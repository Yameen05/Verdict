"""Deterministic answers for "what happens to my $X?" chat questions.

The /research/ask endpoint short-circuits money questions here BEFORE any LLM
call: the answer is computed from stored horizon stats, so it is exact,
grounded, and free. Returns None when the question isn't money-shaped, which
tells the router to fall through to the LLM.
"""

# NOTE: no `from __future__ import annotations` — mirrors routers/ask.py.

import asyncio
import re

from app.observability.logging import get_logger
from app.schemas.research import ResearchResponse
from app.services.metrics_client import HorizonStats, fetch_horizon_stats

log = get_logger(__name__)

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
# Questions asking for reasoning ("why did it say sell?", "explain the verdict")
# need the LLM's judgment, not the dollar-range template — even when they also
# mention selling/holding/value.
_EXPLANATION_WORDS = re.compile(
    r"\bwhy\b|\bexplain\b|\bhow come\b|\bwhat (?:does|do|did)\b.*\bmean\b|"
    r"\breason(?:s|ing)?\b|\bwalk me through\b",
    re.IGNORECASE,
)

_SUFFIX_MULTIPLIERS = {"k": 1_000.0, "m": 1_000_000.0}


def _to_amount(raw: str, suffix: str | None) -> float:
    value = float(raw.replace(",", ""))
    if suffix:
        value *= _SUFFIX_MULTIPLIERS[suffix.lower()]
    return value


def _parse_amount(question: str) -> float | None:
    money = re.search(r"\$\s*([0-9][0-9,]*(?:\.\d+)?)\s?([km])?\b", question, re.IGNORECASE)
    if money:
        return _to_amount(money.group(1), money.group(2))

    dollars = re.search(
        r"\b([0-9][0-9,]*(?:\.\d+)?)\s?([km])?\s*(?:dollars?|usd|bucks?)\b",
        question,
        re.IGNORECASE,
    )
    if dollars:
        return _to_amount(dollars.group(1), dollars.group(2))

    bare_investment = re.search(
        r"\b(?:invested|invest|buy|bought|put)\s+([0-9][0-9,]*(?:\.\d+)?)([km])?\b"
        r"(?!\s*(?:day|days|week|weeks|month|months|year|years)\b)",
        question,
        re.IGNORECASE,
    )
    if bare_investment:
        return _to_amount(bare_investment.group(1), bare_investment.group(2))
    return None


def _looks_like_money_question(question: str, amount: float | None) -> bool:
    """Route to the deterministic calculator only when it can truly answer.

    "Why did it say sell?" or "explain the hold call" mention money words but
    ask for reasoning — the calculator's template would ignore the actual
    question, which reads as the analyst refusing to answer. Those go to the
    LLM, which has the report's justification and dissent.
    """
    if _EXPLANATION_WORDS.search(question):
        return False
    if amount is not None and _MONEY_WORDS.search(question):
        return True
    if _SELL_HOLD_DECISION.search(question):
        return True
    # Position phrasing ("am I up on what I bought?") only fits the template
    # when there's an amount to compute with.
    return bool(
        amount is not None
        and _POSITION_WORDS.search(question)
        and _PAST_POSITION_WORDS.search(question)
    )


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


async def investment_answer(
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
