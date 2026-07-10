"""Conversational follow-up endpoint (POST /research/ask).

Grounded in a prior report, with one LLM tool available: `search_filing`
runs a semantic search over the indexed SEC filing so follow-ups can pull
detail the report doesn't carry. Mounted under the /research prefix.
"""

# NOTE: no `from __future__ import annotations` — see routers/research.py.

import json
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field

from app.config import get_settings
from app.limiter import limiter
from app.observability.cost import record_chat, start_tracking
from app.observability.logging import get_logger, get_request_id
from app.routers.research import _validate_ticker
from app.schemas.research import ResearchResponse
from app.services.investment_answer import investment_answer
from app.services.llm import llm_key_configured, make_llm_client

router = APIRouter()
log = get_logger(__name__)


class ChatTurn(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    ticker: str
    question: str = Field(min_length=2, max_length=2000)
    context: ResearchResponse | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class AskResponse(BaseModel):
    answer: str
    cost_usd: float
    request_id: str
    searched_filing: bool = False




_ASK_SYSTEM = """You are Verdict's analyst — a plain-English guide for a regular
person who just ran a research report on one stock or coin. You receive a
distilled JSON of that report's findings.

THE ONE RULE: answer the question they actually asked, in your FIRST sentence.
Then back it up with 1-4 short sentences using only numbers and facts from the
JSON (or filing excerpts from the tool). Never restate the question, never
answer a different question, never stop at "the report says X".

How to handle the common question shapes:
• "Do I gain or lose / what happens to my $X?" — state the lean from the
  verdict (Buy = leans toward gaining, Sell = leans toward losing, Hold =
  roughly a coin flip). Then the realistic dollar range from
  stats.typical_swing_pct applied to their $X (low = X*(1-swing/100), high =
  X*(1+swing/100)), then the past-year extremes from best/worst_window_pct.
  End with one sentence: exact numbers are unknowable — these are normal swing
  sizes, not promises.
• "Why …?" / "explain …" — give the real drivers: verdict.justification, the
  strongest opposing argument in verdict.dissent, news items, insider buy/sell
  counts, analyst consensus. If they're challenging the call, be honest about
  the other side — the dissent field exists exactly for that.
• "Should I buy/sell/hold?" — translate the verdict + horizon into a lean,
  name the single biggest risk (verdict.key_risks / falsifiers), and note this
  is what the evidence shows, not personal advice.
• "What would change the call?" — use verdict.falsifiers, plainly.
• Company/filing detail the JSON doesn't carry (segments, debt terms, lawsuit
  language) — call the search_filing tool. Never use it for money questions.

Style: plain text, short sentences, real dollars when they gave an amount.
No markdown symbols (no **, no #, no tables); a simple "- " list is fine when
they ask for several things. 2-6 sentences unless they asked for a list.

Honesty: use only what's in the JSON or tool results — never invent a price,
percentage, or headline. If a needed number is missing, say what's missing AND
give the closest thing you do have. Never refuse to answer; always give your
best grounded read. If the question names a different holding period than
stats.horizon_days, answer with what you have and suggest re-running Analyze
for that period.

If the report JSON is null: tell them to pick the asset, choose how long they'd
hold it, and press Analyze. This is not personalized financial advice — you
describe what the evidence shows, you don't know their finances."""


def _clip(text: str | None, limit: int = 400) -> str | None:
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _distill_context(context: ResearchResponse) -> dict[str, Any]:
    """Boil the full ResearchResponse down to what the analyst needs.

    The raw payload (evidence ledger, full debate cases, citation graphs) is
    thousands of tokens of noise that measurably degrades answers — the model
    starts summarizing the report instead of answering the question. Keep the
    verdict, the numbers, and short readable signals.
    """
    report = context.report
    metrics = context.metrics
    signals = context.signals
    return {
        "ticker": context.ticker,
        "verdict": {
            "recommendation": report.recommendation,
            "confidence_0_to_100": report.confidence,
            "horizon_days": report.horizon_days,
            "justification": _clip(report.justification),
            "simple_summary": _clip(report.simple_summary),
            "horizon_outlook": _clip(report.horizon_outlook),
            "key_risks": report.key_risks[:4],
            "falsifiers": report.falsifiers[:3],
            "dissent": _clip(report.dissent),
        },
        "stats": {
            "current_price": metrics.current_price,
            "week_52_low": metrics.week_52_low,
            "week_52_high": metrics.week_52_high,
            "pe_ratio": metrics.pe_ratio,
            "eps": metrics.eps,
            "revenue": metrics.revenue,
            "profit_margin": metrics.profit_margin,
            "debt_to_equity": metrics.debt_to_equity,
            "horizon_days": metrics.horizon_days,
            "typical_swing_pct": metrics.typical_swing_pct,
            "recent_return_pct": metrics.recent_return_pct,
            "best_window_pct": metrics.best_window_pct,
            "worst_window_pct": metrics.worst_window_pct,
        },
        "news": {
            "sentiment_minus1_to_1": context.news.sentiment_score,
            "summary": _clip(context.news.summary),
            "top_headlines": [
                {"title": h.title, "sentiment": h.score}
                for h in context.news.top_headlines[:5]
            ],
        },
        "insiders": {
            "buys": context.insider.buy_count,
            "sells": context.insider.sell_count,
            "summary": _clip(context.insider.summary, 200),
        },
        "market_signals": {
            "analyst_consensus": signals.analyst.consensus if signals.analyst else None,
            "analyst_target": (
                signals.fundamentals.analyst_target if signals.fundamentals else None
            ),
            "retail_sentiment": signals.retail.label if signals.retail else None,
            "macro_regime": signals.macro.regime if signals.macro else None,
            "days_to_earnings": signals.earnings_days,
        },
        "sec_findings": [
            {"question": f.question, "answer": _clip(f.answer, 300)}
            for f in context.sec.findings[:3]
        ],
    }

_SEARCH_FILING_TOOL = {
    "type": "function",
    "function": {
        "name": "search_filing",
        "description": (
            "Semantic search over the indexed SEC filing (10-K/10-Q) for the "
            "current ticker. Returns the most relevant excerpts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look for in the filing",
                }
            },
            "required": ["query"],
        },
    },
}


@lru_cache(maxsize=1)
def _ask_client() -> AsyncOpenAI:
    return make_llm_client()


def _llm_error_detail(e: OpenAIError) -> str:
    """Turn a provider SDK error into a clear, actionable message.

    Distinguishes a hard out-of-quota/billing failure (which retrying never
    fixes) from a transient rate limit — the SDK reports both as
    RateLimitError, which is what made the original failure look like a
    temporary "try again" glitch.
    """
    msg = str(getattr(e, "message", "") or e).lower()
    if any(s in msg for s in ("insufficient_quota", "exceeded your current quota", "billing")):
        return (
            "The AI provider rejected the request: this account is out of "
            "quota/credits. Add billing/credits or switch to a free provider "
            "(e.g. a Google Gemini key). Retrying won't help until then."
        )
    return f"LLM call failed ({type(e).__name__})"


async def _run_filing_search(ticker: str, query: str) -> str:
    """Execute the search_filing tool; failures come back as tool text."""
    from app.services import vectorstore
    from app.services.embeddings import embed_query

    try:
        vector = await embed_query(query)
        matches = await vectorstore.query(ticker, vector, top_k=4)
    except Exception as e:  # noqa: BLE001 - tool result, not endpoint failure
        return f"Filing search failed ({type(e).__name__}). Answer from the report context."
    if not matches:
        return (
            "No indexed filing chunks for this ticker. Tell the user to ingest "
            "a filing first if they need filing-level detail."
        )
    return "\n\n---\n\n".join(m.text[:1000] for m in matches)


@router.post("/ask", response_model=AskResponse)
@limiter.limit(lambda: get_settings().rate_limit_research)
async def ask(request: Request, body: AskRequest) -> AskResponse:
    ticker = _validate_ticker(body.ticker)
    tracker = start_tracking()
    rid = get_request_id()

    calculator_answer = await investment_answer(ticker, body.question.strip(), body.context)
    if calculator_answer is not None:
        log.info(
            "ask_investment_calculator_completed",
            extra={"ticker": ticker, "cost_usd": tracker.total_usd},
        )
        return AskResponse(
            answer=calculator_answer,
            cost_usd=tracker.total_usd,
            request_id=rid,
            searched_filing=False,
        )

    settings = get_settings()
    # Catch missing/placeholder keys early so we return a clean 503 instead of
    # bouncing off the provider SDK.
    if not llm_key_configured(settings.resolved_llm_key):
        raise HTTPException(
            status_code=503,
            detail=(
                "No LLM API key configured. Set LLM_API_KEY (or OPENAI_API_KEY) "
                "in the backend .env and restart. For free Google Gemini, also "
                "set LLM_BASE_URL to its OpenAI-compatible endpoint."
            ),
        )

    grounding: dict[str, Any] = {"ticker": ticker}
    grounding["report"] = (
        _distill_context(body.context) if body.context is not None else None
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _ASK_SYSTEM},
        {
            "role": "user",
            "content": "RESEARCH CONTEXT (JSON):\n" + json.dumps(grounding, default=str),
        },
    ]
    for turn in body.history[-10:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": body.question.strip()})

    searched = False
    try:
        resp = await _ask_client().chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.3,
            max_tokens=700,
            tools=[_SEARCH_FILING_TOOL],
        )
        record_chat(settings.llm_model, resp)
        choice = resp.choices[0]

        tool_calls = getattr(choice.message, "tool_calls", None)
        if tool_calls:
            searched = True
            messages.append(choice.message.model_dump(exclude_none=True))
            for call in tool_calls[:2]:
                try:
                    query = json.loads(call.function.arguments).get("query", "")
                except json.JSONDecodeError:
                    query = ""
                excerpts = await _run_filing_search(ticker, query or body.question)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": excerpts,
                    }
                )
            resp = await _ask_client().chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=0.3,
                max_tokens=700,
            )
            record_chat(settings.llm_model, resp)
            choice = resp.choices[0]

        answer = (choice.message.content or "").strip()
        if not answer:
            # Some models return an empty message (e.g. after deciding not to
            # call a tool). One firm nudge fixes it far more often than asking
            # the user to rephrase.
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Answer the question above directly now, in plain "
                        "text, using the research context."
                    ),
                }
            )
            resp = await _ask_client().chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                temperature=0.3,
                max_tokens=700,
            )
            record_chat(settings.llm_model, resp)
            answer = (resp.choices[0].message.content or "").strip()
    except OpenAIError as e:
        log.exception("ask_llm_failed", extra={"error_type": type(e).__name__})
        raise HTTPException(status_code=502, detail=_llm_error_detail(e)) from e

    answer = answer or (
        "I couldn't put together an answer for that one. Try asking it a "
        "different way, or run Analyze again for fresh context."
    )
    log.info(
        "ask_completed",
        extra={"ticker": ticker, "cost_usd": tracker.total_usd, "searched": searched},
    )
    return AskResponse(
        answer=answer,
        cost_usd=tracker.total_usd,
        request_id=rid,
        searched_filing=searched,
    )
