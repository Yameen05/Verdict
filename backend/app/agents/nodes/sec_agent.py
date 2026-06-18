"""SEC RAG agent node.

For a given ticker, retrieves chunks from the existing Pinecone index for a
fixed set of canonical research questions and uses the configured chat model to
synthesize each set of chunks into a short answer. Output is a `SECFindings`
slot of `ResearchState`.

Assumes the filing has already been ingested via `POST /filings/ingest`. If the
namespace is empty, returns status="skipped" with a helpful error.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from openai import AsyncOpenAI

from app.agents.state import ResearchState
from app.config import get_settings
from app.observability.cost import record_chat
from app.observability.logging import get_logger
from app.schemas.research import SECFinding, SECFindings
from app.services import vectorstore
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


async def sec_agent(state: ResearchState) -> dict:
    ticker = state["ticker"]
    try:
        results = await asyncio.gather(
            *(_answer_one(ticker, q) for q in CANONICAL_QUESTIONS)
        )
    except Exception as e:  # noqa: BLE001
        return {"sec": SECFindings(status="error", error=str(e))}

    findings = [f for f, _ in results]
    accession = next((a for _, a in results if a), None)

    if all(f.source_chunks == 0 for f in findings):
        return {
            "sec": SECFindings(
                status="skipped",
                error=(
                    "No chunks found in Pinecone for this ticker. "
                    "Ingest a filing first via POST /filings/ingest."
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
