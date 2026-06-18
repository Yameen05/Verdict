"""Synthesizer node — Phase 5.

Combines findings from all three specialist agents (SEC RAG, news sentiment,
financial metrics) into a structured ResearchReport with a real Buy/Hold/Sell
recommendation and justification.

The decision logic is intentionally embedded in the system prompt rather than
hard-coded in Python, because:
  1. The signals are heterogeneous (qualitative SEC text + numerical metrics
     + sentiment score) and weighing them is fuzzy reasoning that an LLM
     does better than `if/else`.
  2. Hard-coded thresholds (P/E < X → Buy) overfit to one market regime.

Falls back to "Pending" only when no agent returned usable data.
"""

from __future__ import annotations

import json
from functools import lru_cache

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from app.agents.state import ResearchState
from app.config import get_settings
from app.observability.cost import record_chat
from app.observability.logging import get_logger
from app.schemas.research import ResearchReport
from app.services.llm import make_llm_client

log = get_logger(__name__)

_SYSTEM = """You are a senior financial-research analyst. You receive a JSON
object with findings from three specialist agents:

  • sec:     RAG-retrieved answers from the company's latest 10-K / 10-Q
  • news:    aggregate sentiment score in [-1, 1] over the last 30 days, plus
             a short narrative summary
  • metrics: trailing twelve-month financial figures (revenue, EPS, P/E,
             profit margin, debt-to-equity, 52-week range)

Each agent reports a `status` field. If any agent's status is
`"skipped"`, `"not_implemented"`, or `"error"`, treat that section as
unavailable but still produce the best report you can from the others.

Issue a Buy / Hold / Sell recommendation following this rubric:

  Buy  — Multiple confirming positives: healthy/improving fundamentals
         (e.g. solid margins, reasonable P/E, manageable leverage), positive
         news sentiment (score > 0.1), and manageable risks per the filing.
  Hold — Mixed or balanced signals: ok fundamentals but headwinds, or a
         great business at a stretched valuation, or signals disagree.
  Sell — Multiple confirming negatives: weakening fundamentals (margin
         compression, high leverage, valuation disconnected from earnings),
         negative news sentiment (score < -0.1), or material disclosed risks.

Only output `"Pending"` if zero agents returned usable data.

Be concrete. In the justification, reference the actual numbers and concrete
SEC findings — not generic phrases. Example: "Buy — 28% profit margin and 0.45
debt/equity show capital discipline; 52-week range puts the current
implied price near the lower third; sentiment is mildly positive (0.18)."

Return ONLY a JSON object with this exact shape (no markdown fences):

{
  "recommendation": "Buy" | "Hold" | "Sell" | "Pending",
  "justification":  "2-4 sentences grounded in the specific findings",
  "company_overview": "1-2 sentences from the SEC findings",
  "financial_health": "1-2 sentences citing the actual metrics",
  "key_risks": ["concrete risk 1", "concrete risk 2", ...],
  "news_summary": "1-2 sentences or null"
}
"""


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    return make_llm_client()


def _state_payload(state: ResearchState) -> dict:
    out: dict = {"ticker": state.get("ticker")}
    for key in ("sec", "news", "metrics"):
        val = state.get(key)
        if val is not None:
            out[key] = val.model_dump() if hasattr(val, "model_dump") else val
    return out


def _all_agents_unusable(state: ResearchState) -> bool:
    usable = {"ok"}
    statuses = []
    for key in ("sec", "news", "metrics"):
        val = state.get(key)
        if val is None:
            continue
        s = getattr(val, "status", None) or (val.get("status") if isinstance(val, dict) else None)
        statuses.append(s)
    return bool(statuses) and not any(s in usable for s in statuses)


async def synthesizer(state: ResearchState) -> dict:
    ticker = state["ticker"]
    payload = _state_payload(state)

    # Short-circuit: nothing to reason about.
    if _all_agents_unusable(state):
        return {
            "report": ResearchReport(
                ticker=ticker,
                recommendation="Pending",
                justification=(
                    "No agent returned usable data. Configure API keys "
                    "(LLM / OpenAI embeddings / Pinecone / NewsAPI) and ingest a filing first."
                ),
                company_overview="",
                financial_health="",
            )
        }

    model = get_settings().llm_model
    try:
        resp = await _client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": json.dumps(payload, default=str)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    except OpenAIError as e:
        log.exception("synthesizer_llm_failed", extra={"error_type": type(e).__name__})
        return {
            "report": ResearchReport(
                ticker=ticker,
                recommendation="Pending",
                justification=(
                    f"Synthesizer LLM call failed ({type(e).__name__}). "
                    "Check LLM_API_KEY / OPENAI_API_KEY and provider rate limits."
                ),
                company_overview="",
                financial_health="",
            )
        }
    record_chat(model, resp)
    raw = resp.choices[0].message.content or "{}"

    try:
        data = json.loads(raw)
        report = ResearchReport(
            ticker=ticker,
            recommendation=data.get("recommendation", "Pending"),
            justification=data.get("justification", ""),
            company_overview=data.get("company_overview", ""),
            financial_health=data.get("financial_health", ""),
            key_risks=data.get("key_risks", []) or [],
            news_summary=data.get("news_summary"),
        )
    except (json.JSONDecodeError, ValidationError) as e:
        log.warning("synthesizer_parse_failed", extra={"error": str(e)})
        report = ResearchReport(
            ticker=ticker,
            recommendation="Pending",
            justification=f"Synthesizer failed to parse model output: {e}",
            company_overview="",
            financial_health="",
        )

    return {"report": report}
