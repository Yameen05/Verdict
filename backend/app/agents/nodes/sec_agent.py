"""SEC RAG agent node.

For a given ticker, retrieves chunks from the configured filing index for a
fixed set of canonical research questions and uses the configured chat model to
synthesize each set of chunks into a short answer. Output is a `SECFindings`
slot of `ResearchState`.

Research auto-ingests the latest 10-K before this node runs when the ticker has
no indexed chunks. If the index is still empty, this node returns a user-facing
skip message without exposing API implementation details.
"""

from __future__ import annotations

import asyncio
import re
from functools import lru_cache

from openai import AsyncOpenAI

from app.agents.state import ResearchState
from app.config import get_settings
from app.observability.cost import record_chat
from app.observability.logging import get_logger
from app.schemas.research import SECFinding, SECFindings
from app.services import sec_client, vectorstore
from app.services.chunker import Chunk, chunk_filing
from app.services.embeddings import embed_query
from app.services.llm import make_llm_client

log = get_logger(__name__)

CANONICAL_QUESTIONS: list[str] = [
    "What are the principal risk factors disclosed in the filing?",
    "How does the company describe its primary revenue sources and business segments?",
    "What notable changes in financial position or liquidity does management discuss?",
    "What competitive threats or industry headwinds are called out?",
]

TOP_K = 4

_STOPWORDS = {
    "about",
    "called",
    "changes",
    "company",
    "competitive",
    "describe",
    "disclosed",
    "discuss",
    "does",
    "factors",
    "filing",
    "financial",
    "from",
    "headwinds",
    "industry",
    "liquidity",
    "management",
    "notable",
    "position",
    "primary",
    "principal",
    "question",
    "revenue",
    "risk",
    "risks",
    "sources",
    "threats",
    "what",
}

_SUMMARY_SYSTEM = (
    "You are a financial-research assistant. Given excerpts from an SEC filing "
    "and a question, produce a concise 1-2 sentence answer grounded ONLY in the "
    "excerpts. If the excerpts do not address the question, say so plainly."
)


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    return make_llm_client()


async def _summarize(question: str, chunks: list[str]) -> str:
    if not chunks:
        return "No relevant excerpts were retrieved."
    joined = "\n\n---\n\n".join(c[:1200] for c in chunks)
    model = get_settings().llm_model
    resp = await _client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {
                "role": "user",
                "content": f"Question: {question}\n\nExcerpts:\n{joined}",
            },
        ],
        temperature=0.1,
        max_tokens=200,
    )
    record_chat(model, resp)
    return (resp.choices[0].message.content or "").strip()


async def _answer_one(ticker: str, question: str) -> tuple[SECFinding, str | None]:
    """Return (finding, accession) — accession comes from the first matched chunk if any."""
    vector = await embed_query(question)
    matches = await vectorstore.query(ticker, vector, top_k=TOP_K)
    answer = await _summarize(question, [m.text for m in matches])
    accession = matches[0].metadata.get("accession") if matches else None
    return (
        SECFinding(question=question, answer=answer, source_chunks=len(matches)),
        accession,
    )


def _terms(question: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-z]{4,}", question.lower())
        if word not in _STOPWORDS
    ]


def _select_direct_chunks(chunks: list[Chunk], question: str) -> list[str]:
    terms = _terms(question)
    scored: list[tuple[int, int, Chunk]] = []
    for index, chunk in enumerate(chunks):
        text = chunk.text.lower()
        score = sum(text.count(term) for term in terms)
        if score > 0:
            scored.append((score, index, chunk))
    if not scored:
        return [c.text for c in chunks[:TOP_K]]
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [chunk.text for _, _, chunk in scored[:TOP_K]]


async def _direct_filing_fallback(ticker: str) -> SECFindings:
    filing = await sec_client.fetch_latest_10k(ticker)
    chunks = chunk_filing(filing)
    if not chunks:
        raise RuntimeError("Latest SEC filing produced no readable sections")

    findings: list[SECFinding] = []
    for question in CANONICAL_QUESTIONS:
        selected = _select_direct_chunks(chunks, question)
        answer = await _summarize(question, selected)
        findings.append(
            SECFinding(
                question=question,
                answer=answer,
                source_chunks=len(selected),
            )
        )

    return SECFindings(
        status="ok",
        findings=findings,
        accession=filing.accession,
    )


async def sec_agent(state: ResearchState) -> dict:
    ticker = state["ticker"]

    from app.services.assets import CRYPTO_SKIP_REASON, is_crypto

    if is_crypto(ticker):
        return {"sec": SECFindings(status="skipped", error=CRYPTO_SKIP_REASON)}

    try:
        results = await asyncio.gather(
            *(_answer_one(ticker, q) for q in CANONICAL_QUESTIONS)
        )
    except Exception as e:  # noqa: BLE001
        return {"sec": SECFindings(status="error", error=str(e))}

    findings = [f for f, _ in results]
    accession = next((a for _, a in results if a), None)

    if all(f.source_chunks == 0 for f in findings):
        try:
            return {"sec": await _direct_filing_fallback(ticker)}
        except Exception as e:  # noqa: BLE001 - keep research moving
            log.warning(
                "sec_direct_filing_fallback_failed",
                extra={"ticker": ticker, "reason": str(e)},
            )
        return {
            "sec": SECFindings(
                status="skipped",
                error=(
                    "No SEC filing sections were available for this ticker. "
                    "Verdict tried automatic indexing and a direct filing read, "
                    "but both were unavailable."
                ),
            )
        }

    return {
        "sec": SECFindings(
            status="ok",
            findings=findings,
            accession=accession,
        )
    }
