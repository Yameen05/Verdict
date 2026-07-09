"""Conversational follow-up endpoint (POST /research/ask).

Grounded in a prior report, with one LLM tool available: `search_filing`
runs a semantic search over the indexed SEC filing so follow-ups can pull
detail the report doesn't carry. Mounted under the /research prefix.
"""

# NOTE: no `from __future__ import annotations` — see routers/research.py.

import asyncio
import json
import re
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
from app.services.llm import llm_key_configured, make_llm_client
from app.services.metrics_client import HorizonStats, fetch_horizon_stats

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


_DEFAULT_HORIZONS = (7, 14, 30, 90, 365)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_MONEY_WORDS = re.compile(
    r"\b(invest|invested|investing|bought|buy|put|worth|value|return|gain|"
    r"gaining|lose|losing|loss|profit|sell|hold|holding)\b",
    re.IGNORECASE,
)
_POSITION_WORDS = re.compile(
    r"\b(sell|hold|holding|return|gain|loss|profit|worth|value)\b",
    re.IGNORECASE,
)
_PAST_POSITION_WORDS = re.compile(
    r"\b(invested|bought|put|held|holding)\b",
    re.IGNORECASE,
)
_SELL_HOLD_DECISION = re.compile(
    r"\bshould\s+i\s+(?:sell|hold)\b|\b(?:sell|hold)\s+(?:it|now|rn|right now)\b|"
    r"\bhow\s+long\b.*\bhold\b",
    re.IGNORECASE,
)


def _parse_amount(question: str) -> float | None:
    money = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d+)?)", question)
    if money:
        return float(money.group(1).replace(",", ""))

    dollars = re.search(
        r"\b([0-9][0-9,]*(?:\.\d+)?)\s*(?:dollars?|usd|bucks?)\b",
        question,
        re.IGNORECASE,
    )
    if dollars:
        return float(dollars.group(1).replace(",", ""))

    bare_investment = re.search(
        r"\b(?:invested|invest|buy|bought|put)\s+([0-9][0-9,]*(?:\.\d+)?)\b"
        r"(?!\s*(?:day|days|week|weeks|month|months|year|years)\b)",
        question,
        re.IGNORECASE,
    )
    if bare_investment:
        return float(bare_investment.group(1).replace(",", ""))
    return None


def _looks_like_money_question(question: str, amount: float | None) -> bool:
    if amount is not None and _MONEY_WORDS.search(question):
        return True
    if _SELL_HOLD_DECISION.search(question):
        return True
    return bool(_POSITION_WORDS.search(question) and _PAST_POSITION_WORDS.search(question))


def _number_value(raw: str) -> int | None:
    cleaned = raw.lower()
    if cleaned.isdigit():
        return int(cleaned)
    return _NUMBER_WORDS.get(cleaned)


def _days_from_parts(number: int, unit: str) -> int:
    unit = unit.lower()
    if unit.startswith("day"):
        return number
    if unit.startswith("week"):
        return number * 7
    if unit.startswith("month"):
        return number * 30
    if unit.startswith("year"):
        return number * 365
    return number


def _label_days(days: int | None) -> str:
    if not days:
        return "the report window"
    labels = {
        1: "1 day",
        7: "1 week",
        14: "2 weeks",
        30: "1 month",
        90: "3 months",
        365: "1 year",
    }
    if days in labels:
        return labels[days]
    if days % 365 == 0:
        years = days // 365
        return f"{years} year{'s' if years != 1 else ''}"
    if days % 30 == 0:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''}"
    if days % 7 == 0:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''}"
    return f"{days} days"


def _extract_past_days(question: str) -> int | None:
    q = question.lower()
    if re.search(r"\byesterday\b", q):
        return 1
    if re.search(r"\b(last|past)\s+week\b|\ba\s+week\s+ago\b", q):
        return 7
    if re.search(r"\b(last|past)\s+month\b|\ba\s+month\s+ago\b", q):
        return 30
    if re.search(r"\b(last|past)\s+year\b|\ba\s+year\s+ago\b", q):
        return 365

    match = re.search(
        r"\b([0-9]+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
        r"\s+(day|week|month|year)s?\s+ago\b",
        q,
    )
    if not match:
        return None
    number = _number_value(match.group(1))
    return _days_from_parts(number, match.group(2)) if number else None


def _extract_requested_horizons(question: str, report_days: int | None) -> list[int]:
    q = question.lower()
    horizons: list[int] = []

    for match in re.finditer(
        r"\b([0-9]+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
        r"\s+(day|week|month|year)s?\b",
        q,
    ):
        # "2 weeks ago" describes when the user bought, not a future hold window.
        tail = q[match.end() : match.end() + 8]
        if tail.strip().startswith("ago"):
            continue
        number = _number_value(match.group(1))
        if number:
            horizons.append(_days_from_parts(number, match.group(2)))

    if re.search(r"\bnext\s+week\b", q):
        horizons.append(7)
    if re.search(r"\bnext\s+month\b", q):
        horizons.append(30)
    if re.search(r"\bnext\s+year\b", q):
        horizons.append(365)

    wants_later = bool(
        re.search(r"\b(and on|later|longer|how long|hold for|from here|what about)\b", q)
    )
    if wants_later:
        horizons.extend(_DEFAULT_HORIZONS)

    if not horizons:
        horizons.append(report_days or 14)

    unique: list[int] = []
    for days in horizons:
        if 1 <= days <= 365 and days not in unique:
            unique.append(days)
    return unique


def _fmt_money(value: float) -> str:
    value = round(value + 0.0000001, 2)
    if value.is_integer():
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def _fmt_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_delta(value: float) -> str:
    if abs(value) < 0.005:
        return "$0"
    direction = "gain" if value > 0 else "loss"
    return f"{_fmt_money(abs(value))} {direction}"


def _stats_from_context(context: ResearchResponse, days: int) -> HorizonStats | None:
    metrics = context.metrics
    if metrics.horizon_days != days:
        return None
    if not any(
        value is not None
        for value in (
            metrics.recent_return_pct,
            metrics.typical_swing_pct,
            metrics.best_window_pct,
            metrics.worst_window_pct,
        )
    ):
        return None
    return HorizonStats(
        horizon_days=days,
        recent_return_pct=metrics.recent_return_pct,
        typical_swing_pct=metrics.typical_swing_pct,
        best_window_pct=metrics.best_window_pct,
        worst_window_pct=metrics.worst_window_pct,
    )


async def _stats_for_horizon(
    ticker: str, context: ResearchResponse, days: int
) -> HorizonStats | None:
    context_stats = _stats_from_context(context, days)
    if context_stats is not None:
        return context_stats
    try:
        return await asyncio.to_thread(fetch_horizon_stats, ticker, days)
    except Exception as e:  # noqa: BLE001 - a missing window should not break chat
        log.warning(
            "ask_horizon_stats_unavailable",
            extra={"ticker": ticker, "horizon_days": days, "reason": str(e)},
        )
        return None


def _recommendation_line(recommendation: str, report_days: int | None) -> str:
    window = _label_days(report_days)
    if recommendation == "Buy":
        return (
            f"Plain answer: the report says Buy for {window}, so it leans toward "
            "holding/gaining for that window."
        )
    if recommendation == "Sell":
        return (
            f"Plain answer: the report says Sell for {window}, so it leans toward "
            "selling/avoiding the hold instead of waiting longer."
        )
    if recommendation == "Hold":
        return (
            f"Plain answer: the report says Hold for {window}, so there is no clear "
            "edge; it could go either way."
        )
    return "Plain answer: the report does not have enough confidence to call Buy, Hold, or Sell."


def _hold_length_line(recommendation: str, report_days: int | None) -> str:
    window = _label_days(report_days)
    if recommendation == "Buy":
        return f"How long: use {window} as the checkpoint, then rerun the report."
    if recommendation == "Sell":
        return "How long: this report does not support holding longer; if you keep it, check again soon."
    if recommendation == "Hold":
        return f"How long: there is no strong signal, so reassess around {window} or sooner if news/price changes."
    return "How long: rerun the report when there is enough data for a clear verdict."


def _future_window_line(
    days: int,
    base_amount: float,
    original_amount: float,
    stats: HorizonStats | None,
) -> str:
    label = _label_days(days)
    if stats is None:
        return f"{label}: I do not have enough price history to calculate this window."

    parts: list[str] = []
    if stats.typical_swing_pct is not None:
        swing = abs(stats.typical_swing_pct)
        low = base_amount * (1 - swing / 100)
        high = base_amount * (1 + swing / 100)
        parts.append(f"usually about {_fmt_money(low)}-{_fmt_money(high)}")

    if stats.recent_return_pct is not None:
        repeat_value = base_amount * (1 + stats.recent_return_pct / 100)
        parts.append(
            f"if the latest {label} move repeated: {_fmt_money(repeat_value)} "
            f"({_fmt_delta(repeat_value - original_amount)} vs your original amount)"
        )

    if stats.best_window_pct is not None and stats.worst_window_pct is not None:
        worst = base_amount * (1 + stats.worst_window_pct / 100)
        best = base_amount * (1 + stats.best_window_pct / 100)
        parts.append(f"past-year rough extreme: {_fmt_money(worst)}-{_fmt_money(best)}")

    return f"{label}: " + "; ".join(parts) + "."


async def _investment_answer(
    ticker: str, question: str, context: ResearchResponse | None
) -> str | None:
    amount = _parse_amount(question)
    if not _looks_like_money_question(question, amount):
        return None
    if context is None:
        return (
            "I don't have a fresh report for this one yet. Pick the stock, choose "
            "how long you'd hold it, and hit Analyze first."
        )

    report_days = context.report.horizon_days or context.metrics.horizon_days or 14
    recommendation = context.report.recommendation
    past_days = _extract_past_days(question)
    horizons = _extract_requested_horizons(question, report_days) if amount is not None else []
    stats_by_day = {
        days: await _stats_for_horizon(ticker, context, days)
        for days in sorted(set(horizons + ([past_days] if past_days else [])))
    }

    lines: list[str] = []
    current_value = amount
    if amount is not None:
        if past_days:
            stats = stats_by_day.get(past_days)
            if stats and stats.recent_return_pct is not None:
                current_value = amount * (1 + stats.recent_return_pct / 100)
                lines.append(
                    f"Assuming you invested {_fmt_money(amount)} in {ticker} "
                    f"{_label_days(past_days)} ago, it would be about "
                    f"{_fmt_money(current_value)} right now: "
                    f"{_fmt_delta(current_value - amount)} ({_fmt_pct(stats.recent_return_pct)})."
                )
            else:
                lines.append(
                    f"Assuming you invested {_fmt_money(amount)} in {ticker} "
                    f"{_label_days(past_days)} ago, I cannot calculate the current return "
                    "from the available price history."
                )
        else:
            price = context.metrics.current_price
            share_text = ""
            if price and price > 0:
                share_text = (
                    f" at about {_fmt_money(price)}/share, you would own about "
                    f"{amount / price:.4f} shares"
                )
            lines.append(f"If you put {_fmt_money(amount)} into {ticker} right now{share_text}.")

    lines.append(_recommendation_line(recommendation, report_days))
    lines.append(_hold_length_line(recommendation, report_days))

    if amount is not None:
        base_for_future = current_value if past_days and current_value is not None else amount
        heading = (
            "If you keep holding from today's estimated value:"
            if past_days
            else "What the next windows could look like:"
        )
        lines.append(heading)
        for days in horizons:
            lines.append(
                _future_window_line(
                    days,
                    base_for_future,
                    amount,
                    stats_by_day.get(days),
                )
            )
    else:
        lines.append("I need the dollar amount and when you bought to calculate your return.")

    lines.append("Nobody can know the exact future number; these are past swing ranges, not promises.")
    return "\n".join(lines)


_ASK_SYSTEM = """You are Verdict's analyst assistant, talking to a regular
person who may know nothing about the stock market. The user already ran a
research report. You receive it as JSON — the important parts are:
  • report.recommendation : Buy / Hold / Sell (the verdict)
  • report.horizon_days   : how long the user plans to hold (e.g. 14 = 2 weeks)
  • metrics.current_price : today's price per share
  • metrics.typical_swing_pct : how much the price normally moves over the
        user's window, up OR down (e.g. 7 means ±7%)
  • metrics.recent_return_pct : how it actually moved over the most recent window
  • metrics.best_window_pct / worst_window_pct : best and worst that window did
        in the past year

You also have a `search_filing` tool for questions about the company's official
filing that the report doesn't already answer. Don't use it for money questions.

ANSWER THE QUESTION THEY ACTUALLY ASKED. Talk in plain words and real dollars,
not jargon. Keep it to 2-5 short sentences.

THE MOST COMMON QUESTION — "if I put in $X, do I gain or lose (over my window)?"
Answer it head-on, in this shape:
  1. State the lean from the verdict: Buy = "leans toward gaining", Sell =
     "leans toward losing", Hold = "roughly a coin flip / could go either way".
  2. Give the realistic dollar range using typical_swing_pct on their $X:
     low  = X * (1 - swing/100), high = X * (1 + swing/100).
     e.g. $100 with a 7% typical 2-week swing → "usually between $93 and $107".
  3. Give the rough extremes from best_window_pct / worst_window_pct if present.
  4. One plain-English sentence on WHY (the main reason behind the verdict).
Then always end with: "Nobody can know the exact number — this is the usual
size of the swings, not a promise."

Never say just "the report suggests a Sell" and stop — that does not answer a
money question. Always translate the verdict into gain/lose + a dollar range.

Other rules:
  • Use ONLY numbers in the JSON (or filing excerpts). Never invent a price,
    percentage, or headline. If a needed number is missing, say so plainly.
  • Frame everything for report.horizon_days. If the user names a different
    period than the report was run for, answer with what you have but tell them
    to re-run with that period for an exact match.
  • This is not personalized financial advice; never tell them how much to buy
    or when. The gain/lose framing is about the odds the evidence shows, not a
    guarantee.
  • If the report context is missing/empty, say: "I don't have a fresh report
    for this one yet — pick it, choose how long you'd hold it, and hit Analyze."
"""

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

    investment_answer = await _investment_answer(ticker, body.question.strip(), body.context)
    if investment_answer is not None:
        log.info(
            "ask_investment_calculator_completed",
            extra={"ticker": ticker, "cost_usd": tracker.total_usd},
        )
        return AskResponse(
            answer=investment_answer,
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
    grounding["report"] = body.context.model_dump() if body.context is not None else None

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
            max_tokens=500,
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
                max_tokens=500,
            )
            record_chat(settings.llm_model, resp)
            choice = resp.choices[0]
    except OpenAIError as e:
        log.exception("ask_llm_failed", extra={"error_type": type(e).__name__})
        raise HTTPException(status_code=502, detail=_llm_error_detail(e)) from e

    answer = (choice.message.content or "").strip() or (
        "I couldn't generate a response. Try rephrasing your question."
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
