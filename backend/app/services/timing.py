"""The timing agent — 'should I buy now, wait, or accumulate?'

This is decision-support, NOT prediction. Short-term price movement is close to
a random walk and no signal reliably forecasts it. What this agent does is
disciplined: it reads the chart (services/technicals), pulls recent news, and
translates the *current setup* into a timing stance with an explicit confidence,
rationale, and risks — always framed for the user's holding horizon.

When an LLM is configured it synthesizes technicals + headlines into the stance;
otherwise a transparent rules engine over the technical bias is used. Either way
the deterministic snapshot is returned so the call is auditable, not a black box.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings
from app.observability.logging import get_logger
from app.services.llm import llm_key_configured, make_llm_client
from app.services.metrics_client import (
    MetricsClientError,
    fetch_days_to_earnings,
    fetch_price_history,
)
from app.services.technicals import TechnicalSnapshot, compute_snapshot

log = get_logger(__name__)

TimingAction = Literal["buy_now", "accumulate", "wait_pullback", "wait_watch", "avoid"]

ACTION_LABELS: dict[str, str] = {
    "buy_now": "Buy now",
    "accumulate": "Accumulate gradually",
    "wait_pullback": "Wait for a pullback",
    "wait_watch": "Wait and watch",
    "avoid": "Avoid for now",
}

DISCLAIMER = (
    "Decision-support only, not financial advice. Short-term price moves are "
    "largely unpredictable; this reflects the current setup and its risks, not a "
    "forecast. Size positions to what you can afford to lose."
)


class TimingAssessment(BaseModel):
    ticker: str
    horizon_days: int
    action: TimingAction
    action_label: str
    confidence: int = Field(ge=0, le=100)
    summary: str
    rationale: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    entry_zone_low: float | None = None
    entry_zone_high: float | None = None
    technicals: dict = Field(default_factory=dict)
    headlines: list[str] = Field(default_factory=list)
    as_of: str
    source: Literal["llm", "rules"] = "rules"
    disclaimer: str = DISCLAIMER


class TimingError(RuntimeError):
    pass


def _earnings_imminent(snap: TechnicalSnapshot) -> bool:
    return snap.days_to_earnings is not None and snap.days_to_earnings <= 3


def _rules_action(snap: TechnicalSnapshot) -> tuple[TimingAction, int]:
    overbought = snap.rsi14 is not None and snap.rsi14 >= 70
    oversold = snap.rsi14 is not None and snap.rsi14 <= 30
    if snap.bias == "bullish":
        if overbought:
            return "wait_pullback", 58
        # Don't chase into a binary earnings event.
        if _earnings_imminent(snap):
            return "wait_watch", 55
        return "buy_now", min(80, 55 + 8 * snap.bias_score)
    if snap.bias == "bearish":
        if oversold:
            return "wait_watch", 55
        return "avoid", min(80, 55 + 8 * abs(snap.bias_score))
    # neutral
    if snap.trend == "up" and not _earnings_imminent(snap):
        return "accumulate", 55
    return "wait_watch", 50


def _rules_assessment(
    ticker: str, horizon_days: int, snap: TechnicalSnapshot, headlines: list[str]
) -> TimingAssessment:
    action, confidence = _rules_action(snap)
    entry_low = snap.support
    entry_high = snap.sma20 or snap.close
    summary = (
        f"{ACTION_LABELS[action]}. The setup is {snap.bias} with a "
        f"{snap.trend} trend over your {horizon_days}-day horizon."
    )
    risks: list[str] = []
    if snap.days_to_earnings is not None and snap.days_to_earnings <= 7:
        risks.append(
            f"Earnings in ~{snap.days_to_earnings} day(s) — the price can gap sharply either way."
        )
    if snap.rsi14 is not None and snap.rsi14 >= 70:
        risks.append("Overbought — chasing here risks buying a local top.")
    if snap.dist_from_high_pct is not None and snap.dist_from_high_pct >= -3:
        risks.append("Near the 52-week high; limited room before resistance.")
    if snap.volatility_pct is not None and snap.volatility_pct >= 4:
        risks.append(f"High volatility (~{snap.volatility_pct:.1f}%/day) can whipsaw entries.")
    if not risks:
        risks.append("Even a clean setup can reverse on news; use a stop.")
    return TimingAssessment(
        ticker=ticker,
        horizon_days=horizon_days,
        action=action,
        action_label=ACTION_LABELS[action],
        confidence=confidence,
        summary=summary,
        rationale=snap.signals,
        risks=risks,
        entry_zone_low=min(entry_low, entry_high) if entry_low and entry_high else entry_low,
        entry_zone_high=max(entry_low, entry_high) if entry_low and entry_high else entry_high,
        technicals=asdict(snap),
        headlines=headlines,
        as_of=snap.as_of,
        source="rules",
    )


_SYSTEM = """You are a disciplined trading-timing analyst. You are given a
deterministic technical snapshot of {ticker} and recent news headlines. The user
plans to hold for about {horizon} days.

Decide ONLY among these actions:
  buy_now        — setup favors entering now
  accumulate     — enter gradually / dollar-cost average in
  wait_pullback  — bullish but extended; wait for a dip to a better price
  wait_watch     — unclear; stay out and monitor
  avoid          — setup is poor for a new entry now

Be honest: short-term moves are largely unpredictable. Never imply certainty.
Ground every rationale point in the provided snapshot or headlines. Return STRICT
JSON: {{"action": <one of the above>, "confidence": <0-100 int>, "summary":
<one sentence>, "rationale": [<=4 short strings], "risks": [<=4 short strings],
"suggested_horizon_days": <int>, "entry_zone_low": <number or null>,
"entry_zone_high": <number or null>}}. Keep confidence <= 85; you are not certain."""


async def _llm_assessment(
    ticker: str, horizon_days: int, snap: TechnicalSnapshot, headlines: list[str]
) -> TimingAssessment:
    client = make_llm_client()
    settings = get_settings()
    user_payload = json.dumps(
        {"technicals": asdict(snap), "headlines": headlines[:8]}, default=str
    )
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": _SYSTEM.format(ticker=ticker, horizon=horizon_days)},
            {"role": "user", "content": user_payload},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    action = data.get("action")
    if action not in ACTION_LABELS:
        raise TimingError(f"LLM returned invalid action: {action}")
    return TimingAssessment(
        ticker=ticker,
        horizon_days=int(data.get("suggested_horizon_days") or horizon_days),
        action=action,
        action_label=ACTION_LABELS[action],
        confidence=max(0, min(85, int(data.get("confidence", 50)))),
        summary=str(data.get("summary") or ACTION_LABELS[action]),
        rationale=[str(x) for x in (data.get("rationale") or [])][:4] or snap.signals,
        risks=[str(x) for x in (data.get("risks") or [])][:4],
        entry_zone_low=_opt_float(data.get("entry_zone_low")),
        entry_zone_high=_opt_float(data.get("entry_zone_high")),
        technicals=asdict(snap),
        headlines=headlines,
        as_of=snap.as_of,
        source="llm",
    )


def _opt_float(v: object) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def _best_effort_headlines(ticker: str) -> list[str]:
    try:
        from app.services.news_client import fetch_market_articles

        articles = await fetch_market_articles(ticker, ticker)
        return [a.title for a in articles[:8] if a.title]
    except Exception:  # noqa: BLE001 - news is optional context
        return []


async def assess_timing(ticker: str, horizon_days: int = 14) -> TimingAssessment:
    ticker = ticker.strip().upper()
    if not ticker:
        raise TimingError("Empty ticker")

    try:
        bars, _ = await asyncio.to_thread(fetch_price_history, ticker, "1Y", "1D")
    except MetricsClientError as e:
        raise TimingError(str(e)) from e
    if len(bars) < 20:
        raise TimingError(f"Not enough price history for {ticker} to assess timing")

    snap = compute_snapshot(bars)
    snap.days_to_earnings = await asyncio.to_thread(fetch_days_to_earnings, ticker)
    if snap.days_to_earnings is not None and snap.days_to_earnings <= 7:
        snap.signals.append(
            f"earnings in ~{snap.days_to_earnings} day(s) — a binary event that can gap the price"
        )
    headlines = await _best_effort_headlines(ticker)

    if llm_key_configured(get_settings().resolved_llm_key):
        try:
            return await _llm_assessment(ticker, horizon_days, snap, headlines)
        except (ValidationError, TimingError, json.JSONDecodeError, KeyError) as e:
            log.warning("timing_llm_failed_fallback", extra={"ticker": ticker, "reason": str(e)})
        except Exception:  # noqa: BLE001 - any provider error → deterministic fallback
            log.exception("timing_llm_error_fallback", extra={"ticker": ticker})

    return _rules_assessment(ticker, horizon_days, snap, headlines)
