"""The day-trade desk — multi-agent intraday buy/sell/stand-aside signals.

Five deterministic "desk agents" each read one dimension of the tape (trend,
momentum, volume/VWAP, levels, catalyst) and vote long/short/neutral with
reasons. A risk manager combines the votes, demands confluence, and only
issues a trade with a concrete entry, stop, and target at acceptable
risk/reward — otherwise it says stand aside, which is the correct call most
of the day. When an LLM is configured, a "head trader" prompt that encodes
day-trading discipline synthesizes the final call; the deterministic desk is
always the fallback and is returned alongside for auditability.

Honesty first: intraday moves are mostly noise. This desk cannot predict; it
enforces the discipline (trade with trend, respect VWAP, cut losses at 1R,
skip the lunch chop) that separates gambling from trading.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings
from app.observability.logging import get_logger
from app.services.daytrade_intraday import (
    IntradaySnapshot,
    compute_intraday_snapshot,
    is_crypto,
)
from app.services.llm import llm_key_configured, make_llm_client
from app.services.metrics_client import MetricsClientError, fetch_price_history

log = get_logger(__name__)

DayTradeAction = Literal["long", "short", "stand_aside"]
Vote = Literal["long", "short", "neutral"]

ACTION_LABELS: dict[str, str] = {
    "long": "Buy — go long",
    "short": "Sell — go short",
    "stand_aside": "Stand aside",
}

DISCLAIMER = (
    "Decision-support only, not financial advice. Most intraday moves are "
    "noise; no signal predicts them reliably. Never trade without the stop, "
    "never risk more than ~1% of your account on one idea, and skip the trade "
    "when the desk says stand aside."
)

# Liquid names day traders actually trade; the scanner sweeps these.
SCAN_TICKERS: tuple[str, ...] = (
    "SPY", "QQQ", "TSLA", "NVDA", "AMD", "AAPL", "META", "AMZN",
    "MSFT", "COIN", "PLTR", "HOOD", "MSTR", "BTC-USD", "ETH-USD",
)


class AgentView(BaseModel):
    name: str
    vote: Vote
    score: int  # signed contribution to the desk score
    reasons: list[str] = Field(default_factory=list)


class DayTradeSignal(BaseModel):
    ticker: str
    action: DayTradeAction
    action_label: str
    confidence: int = Field(ge=0, le=100)
    session: str
    session_note: str
    summary: str
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    risk_per_share: float | None = None
    risk_reward: float | None = None
    rationale: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    plan: list[str] = Field(default_factory=list)
    agents: list[AgentView] = Field(default_factory=list)
    technicals: dict = Field(default_factory=dict)
    headlines: list[str] = Field(default_factory=list)
    as_of: str
    source: Literal["llm", "rules"] = "rules"
    disclaimer: str = DISCLAIMER


class ScanRow(BaseModel):
    ticker: str
    action: DayTradeAction
    action_label: str
    confidence: int
    close: float
    score: int
    note: str


class ScanResponse(BaseModel):
    rows: list[ScanRow] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    as_of: str
    note: str = (
        "Rules-only sweep of liquid day-trading names, strongest desk score "
        "first. Open a ticker for the full multi-agent analysis."
    )


class DayTradeError(RuntimeError):
    pass


# ---------------------------------------------------------------- desk agents


def _trend_agent(s: IntradaySnapshot) -> AgentView:
    score = 0
    reasons: list[str] = []
    if s.ema9 is not None and s.ema20 is not None:
        if s.close > s.ema9 > s.ema20:
            score += 2
            reasons.append("price above rising 9/20 EMA stack — intraday uptrend")
        elif s.close < s.ema9 < s.ema20:
            score -= 2
            reasons.append("price below falling 9/20 EMA stack — intraday downtrend")
        else:
            reasons.append("EMAs are tangled — no clean intraday trend")
    if s.prev_high is not None and s.close > s.prev_high:
        score += 1
        reasons.append("trading above yesterday's high — bullish territory")
    elif s.prev_low is not None and s.close < s.prev_low:
        score -= 1
        reasons.append("trading below yesterday's low — bearish territory")
    vote: Vote = "long" if score >= 2 else "short" if score <= -2 else "neutral"
    return AgentView(name="Trend", vote=vote, score=score, reasons=reasons)


def _momentum_agent(s: IntradaySnapshot) -> AgentView:
    score = 0
    reasons: list[str] = []
    if s.rsi14_5m is not None:
        if s.rsi14_5m >= 75:
            score -= 1
            reasons.append(f"5m RSI {s.rsi14_5m:.0f} — overextended, chasing here is late")
        elif s.rsi14_5m >= 55:
            score += 1
            reasons.append(f"5m RSI {s.rsi14_5m:.0f} — bullish momentum with room")
        elif s.rsi14_5m <= 25:
            score += 1
            reasons.append(f"5m RSI {s.rsi14_5m:.0f} — washed out, bounce risk for shorts")
        elif s.rsi14_5m <= 45:
            score -= 1
            reasons.append(f"5m RSI {s.rsi14_5m:.0f} — bearish momentum")
        else:
            reasons.append(f"5m RSI {s.rsi14_5m:.0f} — neutral")
    if s.macd_hist_5m is not None:
        if s.macd_hist_5m > 0:
            score += 1
            reasons.append("5m MACD above signal — momentum favors longs")
        else:
            score -= 1
            reasons.append("5m MACD below signal — momentum favors shorts")
    vote: Vote = "long" if score >= 2 else "short" if score <= -2 else "neutral"
    return AgentView(name="Momentum", vote=vote, score=score, reasons=reasons)


def _volume_agent(s: IntradaySnapshot) -> AgentView:
    score = 0
    reasons: list[str] = []
    if s.vwap is not None and s.vwap_dist_pct is not None:
        if s.vwap_dist_pct > 0.05:
            score += 2
            reasons.append(f"price {s.vwap_dist_pct:+.2f}% above VWAP — buyers in control")
        elif s.vwap_dist_pct < -0.05:
            score -= 2
            reasons.append(f"price {s.vwap_dist_pct:+.2f}% below VWAP — sellers in control")
        else:
            reasons.append("pinned to VWAP — the market hasn't picked a side")
    if s.rel_volume is not None:
        if s.rel_volume >= 1.5:
            score += 1 if score > 0 else -1 if score < 0 else 0
            reasons.append(f"volume {s.rel_volume:.1f}× normal — real participation")
        elif s.rel_volume <= 0.6:
            reasons.append(
                f"volume only {s.rel_volume:.1f}× normal — thin tape, moves don't stick"
            )
    vote: Vote = "long" if score >= 2 else "short" if score <= -2 else "neutral"
    return AgentView(name="Volume / VWAP", vote=vote, score=score, reasons=reasons)


def _levels_agent(s: IntradaySnapshot) -> AgentView:
    score = 0
    reasons: list[str] = []
    if s.or_high is not None and s.or_low is not None:
        if s.close > s.or_high:
            score += 2
            reasons.append("opening-range breakout is holding above the range")
        elif s.close < s.or_low:
            score -= 2
            reasons.append("opening-range breakdown is holding below the range")
        else:
            reasons.append("still inside the opening range — breakout unconfirmed")
    if (
        s.day_high is not None
        and s.atr_5m is not None
        and s.close >= s.day_high - 0.25 * s.atr_5m
    ):
        reasons.append("pressing the high of day — breakout or double-top, be quick")
    if (
        s.day_low is not None
        and s.atr_5m is not None
        and s.close <= s.day_low + 0.25 * s.atr_5m
    ):
        reasons.append("pressing the low of day — breakdown or double-bottom, be quick")
    vote: Vote = "long" if score >= 2 else "short" if score <= -2 else "neutral"
    return AgentView(name="Levels", vote=vote, score=score, reasons=reasons)


def _catalyst_agent(s: IntradaySnapshot, headlines: list[str]) -> AgentView:
    score = 0
    reasons: list[str] = []
    if s.gap_pct is not None and abs(s.gap_pct) >= 1.0:
        direction = "up" if s.gap_pct > 0 else "down"
        held = (
            s.gap_pct > 0
            and s.day_open is not None
            and s.close >= s.day_open
        ) or (
            s.gap_pct < 0
            and s.day_open is not None
            and s.close <= s.day_open
        )
        if held:
            score += 1 if s.gap_pct > 0 else -1
            reasons.append(f"gapped {direction} {abs(s.gap_pct):.1f}% and the gap is holding")
        else:
            reasons.append(
                f"gapped {direction} {abs(s.gap_pct):.1f}% but it's fading — gap-fill risk"
            )
    if headlines:
        reasons.append(f"news flow present ({len(headlines)} recent headlines) — expect volatility")
    if not reasons:
        reasons.append("no obvious catalyst — technicals are the whole story today")
    vote: Vote = "long" if score >= 1 else "short" if score <= -1 else "neutral"
    return AgentView(name="Catalyst", vote=vote, score=score, reasons=reasons)


def run_desk(s: IntradaySnapshot, headlines: list[str]) -> list[AgentView]:
    return [
        _trend_agent(s),
        _momentum_agent(s),
        _volume_agent(s),
        _levels_agent(s),
        _catalyst_agent(s, headlines),
    ]


# ------------------------------------------------------------- risk manager


def _round_px(v: float) -> float:
    return round(v, 4 if v < 5 else 2)


def _risk_plan(
    action: DayTradeAction, s: IntradaySnapshot
) -> tuple[float | None, float | None, float | None, float | None, list[str]]:
    """Entry, stop, target, R:R and plan notes. Structure-based stops capped by ATR."""
    if action == "stand_aside" or s.atr_5m is None or s.atr_5m <= 0:
        return None, None, None, None, []
    atr = s.atr_5m
    close = s.close
    plan: list[str] = []

    if action == "long":
        entry = close
        if s.ema9 is not None and close - s.ema9 > 1.2 * atr:
            entry = _round_px(s.ema9)
            plan.append("price is extended — use a limit order at the 9 EMA, don't chase")
        supports = [
            lv for lv in (s.or_low, s.vwap, s.prev_low, s.day_low) if lv is not None and lv < entry
        ]
        stop = (max(supports) - 0.25 * atr) if supports else entry - 1.2 * atr
        stop = max(stop, entry - 2.0 * atr)  # never risk more than 2 ATR
        stop = min(stop, entry - 0.5 * atr)  # never tighter than noise
        risk = entry - stop
        target = entry + 2.0 * risk
        # Overhead levels cap the target — but a level price is already breaking
        # (close at/near the high of day) is not resistance, it's blue sky.
        levels_above = [s.prev_high]
        if s.day_high is not None and s.close < s.day_high - 0.5 * atr:
            levels_above.append(s.day_high)
        resistances = [lv for lv in levels_above if lv is not None and lv > entry + 0.1 * atr]
        if resistances:
            nearest = min(resistances)
            if nearest < target:
                target = nearest - 0.1 * atr
        rr = (target - entry) / risk if risk > 0 else None
        plan.append("stop goes below structure (opening range / VWAP), not a round number")
    else:
        entry = close
        if s.ema9 is not None and s.ema9 - close > 1.2 * atr:
            entry = _round_px(s.ema9)
            plan.append("price is extended down — short the bounce into the 9 EMA, don't chase")
        resistances = [
            lv
            for lv in (s.or_high, s.vwap, s.prev_high, s.day_high)
            if lv is not None and lv > entry
        ]
        stop = (min(resistances) + 0.25 * atr) if resistances else entry + 1.2 * atr
        stop = min(stop, entry + 2.0 * atr)
        stop = max(stop, entry + 0.5 * atr)
        risk = stop - entry
        target = entry - 2.0 * risk
        # Mirror of the long case: a low the price is actively breaking is not support.
        levels_below = [s.prev_low]
        if s.day_low is not None and s.close > s.day_low + 0.5 * atr:
            levels_below.append(s.day_low)
        supports = [lv for lv in levels_below if lv is not None and lv < entry - 0.1 * atr]
        if supports:
            nearest = max(supports)
            if nearest > target:
                target = nearest + 0.1 * atr
        rr = (entry - target) / risk if risk > 0 else None

    plan.append("take half off at 1R and move the stop to break-even")
    plan.append("if the setup hasn't worked in ~30 minutes, scratch it — time stop")
    return _round_px(entry), _round_px(stop), _round_px(target), (
        round(rr, 2) if rr is not None else None
    ), plan


def rules_signal(
    ticker: str, s: IntradaySnapshot, agents: list[AgentView], headlines: list[str]
) -> DayTradeSignal:
    total = sum(a.score for a in agents)
    longs = sum(1 for a in agents if a.vote == "long")
    shorts = sum(1 for a in agents if a.vote == "short")

    tradable_session = s.session in {"opening_drive", "morning", "afternoon", "power_hour", "open_24_7"}
    threshold = 4 if s.session == "lunch" else 3  # demand more in the chop

    action: DayTradeAction = "stand_aside"
    if tradable_session or s.session == "lunch":
        if total >= threshold and longs >= 2 and shorts == 0:
            action = "long"
        elif total <= -threshold and shorts >= 2 and longs == 0:
            action = "short"

    risks: list[str] = []
    if s.session in {"closed", "after_hours", "premarket"}:
        risks.append("The regular session is not open — this is a plan for the next open, not a live entry.")
    if s.rel_volume is not None and s.rel_volume <= 0.6:
        risks.append("Volume is thin; breakouts fail more often without participation.")
    if s.data_age_minutes is not None and s.data_age_minutes > 20 and tradable_session:
        risks.append(f"Quote is ~{s.data_age_minutes:.0f} min old — confirm price before acting.")
    if s.atr_pct is not None and s.atr_pct >= 1.0:
        risks.append(f"Very volatile tape (~{s.atr_pct:.1f}% per 5m ATR) — halve your size.")

    entry, stop, target, rr, plan = _risk_plan(action, s)
    if action != "stand_aside" and (rr is None or rr < 1.3):
        risks.append("Nearest level caps the trade below 1.3R — the desk passes on poor risk/reward.")
        action = "stand_aside"
        entry = stop = target = rr = None
        plan = []

    confluence = longs if action == "long" else shorts if action == "short" else 0
    if action == "stand_aside":
        confidence = 60
        summary = (
            "No trade. The desk needs multiple agents agreeing with acceptable "
            "risk/reward, and this tape doesn't offer that right now."
        )
    else:
        confidence = min(80, 48 + 5 * abs(total) + 4 * confluence)
        summary = (
            f"{ACTION_LABELS[action]}: {confluence} of 5 desk agents align "
            f"(score {total:+d}) during {s.session.replace('_', ' ')}."
        )

    rationale = [f"{a.name}: {a.reasons[0]}" for a in agents if a.reasons][:6]
    if not risks:
        risks.append("Even A+ setups fail ~40–50% of the time; the stop is the strategy.")

    return DayTradeSignal(
        ticker=ticker,
        action=action,
        action_label=ACTION_LABELS[action],
        confidence=confidence,
        session=s.session,
        session_note=s.session_note,
        summary=summary,
        entry=entry,
        stop=stop,
        target=target,
        risk_per_share=round(abs(entry - stop), 4) if entry is not None and stop is not None else None,
        risk_reward=rr,
        rationale=rationale,
        risks=risks[:5],
        plan=plan,
        agents=agents,
        technicals=asdict(s),
        headlines=headlines[:6],
        as_of=s.as_of,
        source="rules",
    )


# --------------------------------------------------------------- LLM head trader

_SYSTEM = """You are the head trader of a disciplined intraday desk analyzing {ticker}.
Five desk agents (trend, momentum, volume/VWAP, levels, catalyst) have voted, and you
have a deterministic intraday snapshot (VWAP, EMAs, opening range, prior-day levels,
ATR, relative volume, session phase) plus recent headlines.

You know the rules of day trading and you enforce them:
- The trend and VWAP side is the only side to trade. Longs above VWAP, shorts below.
- Opening-range breakouts need volume confirmation; thin tape breakouts fail.
- The first hour and power hour are tradable; lunch (12–2 ET) is chop — mostly pass.
- Never chase an extended move; wait for the pullback to the 9 EMA or VWAP.
- Every trade has a structure-based stop BEFORE entry; minimum 1.5R reward or pass.
- Gaps that hold above the open tend to go; gaps that fade fill.
- When agents disagree, standing aside IS the trade. Most of the day there is no trade.
- You cannot predict; you manage risk. Never imply certainty.

Decide ONLY among: "long" (buy), "short" (sell/short), "stand_aside".
If the session is closed/premarket/after-hours, you may only output stand_aside
(framed as a plan for the next open).

Return STRICT JSON:
{{"action": "long|short|stand_aside", "confidence": <0-100 int, max 85>,
"summary": <one honest sentence>, "entry": <number or null>, "stop": <number or null>,
"target": <number or null>, "rationale": [<=5 short strings grounded in the data],
"risks": [<=4 short strings], "plan": [<=4 short imperative execution steps]}}.
For long: stop < entry < target. For short: target < entry < stop. Numbers near the
current price and levels provided — never invent price levels."""


def _coherent(action: str, entry: float | None, stop: float | None, target: float | None) -> bool:
    if action == "stand_aside":
        return True
    if entry is None or stop is None or target is None:
        return False
    return (stop < entry < target) if action == "long" else (target < entry < stop)


async def _llm_signal(
    ticker: str,
    s: IntradaySnapshot,
    agents: list[AgentView],
    headlines: list[str],
    fallback: DayTradeSignal,
) -> DayTradeSignal:
    client = make_llm_client()
    settings = get_settings()
    payload = json.dumps(
        {
            "snapshot": asdict(s),
            "desk_votes": [a.model_dump() for a in agents],
            "deterministic_desk_call": fallback.action,
            "headlines": headlines[:6],
        },
        default=str,
    )
    resp = await client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": _SYSTEM.format(ticker=ticker)},
            {"role": "user", "content": payload},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    action = data.get("action")
    if action not in ACTION_LABELS:
        raise DayTradeError(f"LLM returned invalid action: {action}")
    if s.session in {"closed", "after_hours", "premarket"} and action != "stand_aside":
        action = "stand_aside"

    def _f(v: object) -> float | None:
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    entry, stop, target = _f(data.get("entry")), _f(data.get("stop")), _f(data.get("target"))
    if not _coherent(action, entry, stop, target):
        # Keep the LLM's read but the desk's deterministic numbers.
        entry, stop, target = fallback.entry, fallback.stop, fallback.target
        if not _coherent(action, entry, stop, target):
            raise DayTradeError("LLM levels incoherent and no deterministic plan")
    risk = abs(entry - stop) if entry is not None and stop is not None else None
    rr = (
        round(abs(target - entry) / risk, 2)
        if risk and target is not None and entry is not None
        else None
    )
    return DayTradeSignal(
        ticker=ticker,
        action=action,
        action_label=ACTION_LABELS[action],
        confidence=max(0, min(85, int(data.get("confidence", 50)))),
        session=s.session,
        session_note=s.session_note,
        summary=str(data.get("summary") or ACTION_LABELS[action]),
        entry=entry,
        stop=stop,
        target=target,
        risk_per_share=round(risk, 4) if risk else None,
        risk_reward=rr,
        rationale=[str(x) for x in (data.get("rationale") or [])][:5] or fallback.rationale,
        risks=[str(x) for x in (data.get("risks") or [])][:4] or fallback.risks,
        plan=[str(x) for x in (data.get("plan") or [])][:4] or fallback.plan,
        agents=agents,
        technicals=asdict(s),
        headlines=headlines[:6],
        as_of=s.as_of,
        source="llm",
    )


# ------------------------------------------------------------------ public API


async def _best_effort_headlines(ticker: str) -> list[str]:
    try:
        from app.services.news_client import fetch_market_articles

        articles = await fetch_market_articles(ticker, ticker)
        return [a.title for a in articles[:6] if a.title]
    except Exception:  # noqa: BLE001 - news is optional context
        return []


async def assess_daytrade(ticker: str, now: datetime | None = None) -> DayTradeSignal:
    ticker = ticker.strip().upper()
    if not ticker:
        raise DayTradeError("Empty ticker")
    try:
        bars, _ = await asyncio.to_thread(fetch_price_history, ticker, "5D", "5M")
    except MetricsClientError as e:
        raise DayTradeError(str(e)) from e
    if len(bars) < 30:
        raise DayTradeError(f"Not enough intraday data for {ticker} to run the desk")

    snap = compute_intraday_snapshot(ticker, bars, now)
    headlines = await _best_effort_headlines(ticker)
    agents = run_desk(snap, headlines)
    fallback = rules_signal(ticker, snap, agents, headlines)

    if llm_key_configured(get_settings().resolved_llm_key):
        try:
            return await _llm_signal(ticker, snap, agents, headlines, fallback)
        except (ValidationError, DayTradeError, json.JSONDecodeError, KeyError) as e:
            log.warning("daytrade_llm_failed_fallback", extra={"ticker": ticker, "reason": str(e)})
        except Exception:  # noqa: BLE001 - any provider error → deterministic desk
            log.exception("daytrade_llm_error_fallback", extra={"ticker": ticker})
    return fallback


async def scan_daytrade(now: datetime | None = None) -> ScanResponse:
    """Rules-only sweep of the liquid list; no LLM and no news calls."""

    async def one(ticker: str) -> ScanRow | None:
        try:
            bars, _ = await asyncio.to_thread(fetch_price_history, ticker, "5D", "5M")
            if len(bars) < 30:
                return None
            snap = compute_intraday_snapshot(ticker, bars, now)
            agents = run_desk(snap, [])
            sig = rules_signal(ticker, snap, agents, [])
            total = sum(a.score for a in agents)
            note = sig.rationale[0] if sig.rationale else sig.summary
            return ScanRow(
                ticker=ticker,
                action=sig.action,
                action_label=ACTION_LABELS[sig.action],
                confidence=sig.confidence,
                close=snap.close,
                score=total,
                note=note,
            )
        except (MetricsClientError, ValueError):
            return None

    results = await asyncio.gather(*(one(t) for t in SCAN_TICKERS))
    rows = [r for r in results if r is not None]
    skipped = [t for t, r in zip(SCAN_TICKERS, results, strict=True) if r is None]
    rows.sort(key=lambda r: (r.action == "stand_aside", -abs(r.score), -r.confidence))
    return ScanResponse(
        rows=rows,
        skipped=skipped,
        as_of=datetime.now().isoformat(timespec="seconds"),
    )
