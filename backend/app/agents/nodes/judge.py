"""The Judge — weighs the bull and bear cases and issues the verdict.

Replaces the single-pass synthesizer. The judge receives the evidence ledger
plus both advocates' cases and must:
  • pick Buy / Hold / Sell with a 0-100 confidence,
  • state the strongest opposing argument it overruled (dissent),
  • list falsifiers — concrete observations that would flip the verdict,
  • score five dimensions 0-10 for the scorecard,
  • cite evidence ids for its key claims.

Reflection loop: on the first pass the judge may instead request ONE targeted
follow-up retrieval from the indexed SEC filing (`needs_evidence`). The
`followup` node runs that query, appends the excerpts to the ledger, and the
judge decides again — this time final.

The decision logic stays in the prompt rather than Python if/else because the
signals are heterogeneous and hard-coded thresholds overfit one market regime.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache

from langgraph.config import get_stream_writer
from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from app.agents.state import ResearchState
from app.config import get_settings
from app.observability.cost import record_chat
from app.observability.logging import get_logger
from app.schemas.research import (
    Argument,
    DimensionScores,
    EvidenceItem,
    ResearchReport,
)
from app.services.llm import make_llm_client

log = get_logger(__name__)

MAX_REFLECTIONS = 1


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    return make_llm_client()


def _writer() -> Callable[[dict], None]:
    try:
        return get_stream_writer()
    except Exception:  # noqa: BLE001 - direct node calls have no graph context
        return lambda _payload: None


_SYSTEM = """You are the judge in an adversarial equity-research debate about
{ticker}. You receive:
  • an evidence ledger — lines of the form  [id] label: content
  • the bull advocate's case and the bear advocate's case, each citing ids
  • optionally, the verdict from a prior research run for comparison

Weigh both cases against the evidence and issue the verdict.

Rubric:
  Buy  — the bull case rests on multiple confirming positives the bear case
         cannot neutralize (healthy fundamentals, reasonable valuation,
         supportive sentiment/insider signals, manageable disclosed risks).
  Sell — the bear case has confirming negatives the bull case cannot
         neutralize (weakening fundamentals, stretched valuation, negative
         sentiment, material disclosed risks, insider distribution).
  Hold — the cases genuinely balance, or the decisive evidence is missing.
Only use "Pending" if the ledger is empty.

Confidence (0-100): how decisively the winning case beats the losing one.
40 or below means the evidence barely separates them; 80+ means one side had
no real answer.

Be concrete everywhere — cite actual numbers and specific findings, never
generic phrases.{followup_clause}

Return ONLY a JSON object (no markdown fences):
{{
  "recommendation": "Buy" | "Hold" | "Sell",
  "confidence": <int 0-100>,
  "justification": "2-4 sentences: why the winning case won",
  "dissent": "the single strongest opposing argument you overruled, and why it did not carry",
  "falsifiers": ["concrete future observation that would flip this verdict", "…2-4 items"],
  "scores": {{"valuation": <0-10 or null>, "growth": <0-10 or null>,
             "profitability": <0-10 or null>, "balance_sheet": <0-10 or null>,
             "sentiment": <0-10 or null>}},
  "citations": [{{"claim": "key claim from your reasoning", "evidence": ["id", "…"]}}],
  "company_overview": "1-2 sentences from the SEC evidence",
  "financial_health": "1-2 sentences citing the actual metrics",
  "key_risks": ["concrete risk 1", "concrete risk 2"],
  "news_summary": "1-2 sentences or null",
  "delta_summary": "if a prior run is provided: 1-2 sentences on what changed since it, else null"{needs_evidence_field}
}}
"""

_NEEDS_EVIDENCE_CLAUSE = """

If — and only if — one specific missing fact from the SEC filing prevents a
confident verdict, you may instead request ONE follow-up retrieval by
returning `needs_evidence` as a short, targeted question about the filing and
null for `recommendation`. Use this sparingly; most verdicts should be issued
from the evidence you already have."""

_NEEDS_EVIDENCE_FIELD = """,
  "needs_evidence": "targeted question about the filing, or null\""""


def _all_agents_unusable(state: ResearchState) -> bool:
    statuses = []
    for key in ("sec", "news", "metrics", "insider"):
        val = state.get(key)
        if val is None:
            continue
        statuses.append(getattr(val, "status", None))
    return bool(statuses) and not any(s == "ok" for s in statuses)


def _pending(ticker: str, justification: str) -> dict:
    return {
        "report": ResearchReport(
            ticker=ticker,
            recommendation="Pending",
            justification=justification,
            company_overview="",
            financial_health="",
        ),
        "followup_question": None,
    }


def _ledger_lines(evidence: list[EvidenceItem]) -> str:
    return "\n".join(f"[{e.id}] {e.label}: {e.content}" for e in evidence)


def _user_payload(state: ResearchState) -> str:
    parts: list[str] = ["EVIDENCE LEDGER:", _ledger_lines(state.get("evidence") or [])]
    for key, title in (("bull", "BULL CASE"), ("bear", "BEAR CASE")):
        case = state.get(key)
        if case is None or case.status != "ok":
            err = getattr(case, "error", None) if case else None
            parts.append(f"\n{title}: unavailable ({err or 'advocate did not run'})")
            continue
        args = "\n".join(
            f"  - {a.claim} [cites: {', '.join(a.evidence) or 'none'}]"
            for a in case.arguments
        )
        parts.append(f"\n{title}:\nThesis: {case.thesis}\n{args}")
    prior = state.get("prior_run")
    if prior:
        parts.append(
            "\nPRIOR RUN ({date}): {rec} — {just}".format(
                date=str(prior.get("created_at", ""))[:10],
                rec=prior.get("recommendation", "?"),
                just=str(prior.get("justification", ""))[:400],
            )
        )
    return "\n".join(parts)


def _coerce_scores(raw: object) -> DimensionScores | None:
    if not isinstance(raw, dict):
        return None
    try:
        return DimensionScores(
            **{
                k: raw.get(k)
                for k in (
                    "valuation",
                    "growth",
                    "profitability",
                    "balance_sheet",
                    "sentiment",
                )
            }
        )
    except ValidationError:
        return None


def _coerce_citations(raw: object, known_ids: set[str]) -> list[Argument]:
    if not isinstance(raw, list):
        return []
    out: list[Argument] = []
    for a in raw[:8]:
        if not isinstance(a, dict) or not str(a.get("claim", "")).strip():
            continue
        out.append(
            Argument(
                claim=str(a["claim"]).strip(),
                evidence=[i for i in (a.get("evidence") or []) if i in known_ids],
            )
        )
    return out


async def judge(state: ResearchState) -> dict:
    ticker = state["ticker"]
    reflections = state.get("reflection_count", 0)

    if _all_agents_unusable(state):
        return _pending(
            ticker,
            "No agent returned usable data. Configure API keys "
            "(LLM / OpenAI embeddings / NewsAPI) and ingest a filing first.",
        )

    _writer()(
        {"kind": "judge_phase", "phase": "deliberating", "reflection": reflections}
    )

    may_reflect = reflections < MAX_REFLECTIONS and (
        state.get("sec") is not None and state["sec"].status == "ok"
    )
    system = _SYSTEM.format(
        ticker=ticker,
        followup_clause=_NEEDS_EVIDENCE_CLAUSE if may_reflect else "",
        needs_evidence_field=_NEEDS_EVIDENCE_FIELD if may_reflect else "",
    )

    model = get_settings().llm_model
    try:
        resp = await _client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": _user_payload(state)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except OpenAIError as e:
        log.exception("judge_llm_failed", extra={"error_type": type(e).__name__})
        return _pending(
            ticker,
            f"Judge LLM call failed ({type(e).__name__}). "
            "Check LLM_API_KEY / OPENAI_API_KEY and provider rate limits.",
        )
    record_chat(model, resp)

    try:
        data = json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError as e:
        log.warning("judge_parse_failed", extra={"error": str(e)})
        return _pending(ticker, f"Judge failed to parse model output: {e}")

    needs = data.get("needs_evidence")
    if may_reflect and isinstance(needs, str) and needs.strip():
        question = needs.strip()[:300]
        _writer()({"kind": "judge_phase", "phase": "followup", "question": question})
        log.info("judge_requested_followup", extra={"ticker": ticker, "q": question})
        return {"followup_question": question, "reflection_count": reflections + 1}

    known_ids = {e.id for e in (state.get("evidence") or [])}
    try:
        rec = data.get("recommendation")
        report = ResearchReport(
            ticker=ticker,
            recommendation=rec if rec in ("Buy", "Hold", "Sell") else "Pending",
            justification=str(data.get("justification", "") or ""),
            company_overview=str(data.get("company_overview", "") or ""),
            financial_health=str(data.get("financial_health", "") or ""),
            key_risks=[str(r) for r in (data.get("key_risks") or [])][:8],
            news_summary=data.get("news_summary"),
            confidence=_coerce_confidence(data.get("confidence")),
            scores=_coerce_scores(data.get("scores")),
            falsifiers=[str(f) for f in (data.get("falsifiers") or [])][:4],
            dissent=data.get("dissent"),
            citations=_coerce_citations(data.get("citations"), known_ids),
            delta_summary=data.get("delta_summary") if state.get("prior_run") else None,
        )
    except ValidationError as e:
        log.warning("judge_report_invalid", extra={"error": str(e)})
        return _pending(ticker, f"Judge produced an invalid report: {e}")

    return {"report": report, "followup_question": None}


def _coerce_confidence(raw: object) -> int | None:
    try:
        return max(0, min(100, int(raw)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# ----- reflection follow-up -----

async def followup(state: ResearchState) -> dict:
    """Run the judge's one targeted RAG query and append excerpts as evidence."""
    from app.services import vectorstore
    from app.services.embeddings import embed_query

    question = (state.get("followup_question") or "").strip()
    evidence = list(state.get("evidence") or [])
    if not question:
        return {"followup_question": None}

    try:
        vector = await embed_query(question)
        matches = await vectorstore.query(state["ticker"], vector, top_k=3)
    except Exception as e:  # noqa: BLE001 - reflection is best-effort
        log.warning("followup_retrieval_failed", extra={"error": str(e)})
        evidence.append(
            EvidenceItem(
                id="sec:f0",
                source="sec",
                label=f"Follow-up: {question}",
                content=f"Retrieval failed ({type(e).__name__}); decide from existing evidence.",
            )
        )
        return {"evidence": evidence, "followup_question": None}

    if not matches:
        evidence.append(
            EvidenceItem(
                id="sec:f0",
                source="sec",
                label=f"Follow-up: {question}",
                content="The filing index returned no relevant excerpts.",
            )
        )
    for i, m in enumerate(matches):
        evidence.append(
            EvidenceItem(
                id=f"sec:f{i}",
                source="sec",
                label=f"Follow-up: {question}",
                content=m.text[:700],
            )
        )
    _writer()(
        {"kind": "judge_phase", "phase": "followup_done", "chunks": len(matches)}
    )
    return {"evidence": evidence, "followup_question": None}


def route_after_judge(state: ResearchState) -> str:
    return "followup" if state.get("followup_question") else "__end__"
