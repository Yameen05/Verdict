"""Deterministic intraday snapshot for the day-trade desk.

Pure functions over intraday price bars — no I/O. Computes the numbers a day
trader actually stares at: VWAP, fast EMAs, the opening range, prior-day
levels, intraday ATR, relative volume, and the session phase on the US market
clock (crypto trades around the clock). services/daytrade.py feeds this to the
desk agents and the LLM head trader.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.services.metrics_client import PriceBar
from app.services.technicals import _ema, _macd_hist, _rsi

ET = ZoneInfo("America/New_York")

# Session phases, in plain trader language.
SESSION_NOTES: dict[str, str] = {
    "open_24_7": "Crypto trades around the clock; levels use the UTC day.",
    "premarket": "Pre-market — thin liquidity, spreads are wide, moves fake out.",
    "opening_drive": "First hour — highest volume and follow-through of the day.",
    "morning": "Mid-morning — trends from the open often continue or first pull back.",
    "lunch": "Lunch chop (12–2 ET) — volume dries up; most setups fail here.",
    "afternoon": "Early afternoon — watch for the trend to resume off lunch ranges.",
    "power_hour": "Power hour — institutions rebalance; moves get real again.",
    "after_hours": "After hours — the day session is over; plan the next open.",
    "closed": "Market closed — analysis reflects the last session; plan, don't chase.",
}


def is_crypto(ticker: str) -> bool:
    return ticker.upper().endswith("-USD")


def parse_bar_time(iso: str) -> datetime:
    """Bar times are ISO strings; treat naive stamps as UTC."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def session_phase(ticker: str, now: datetime | None = None) -> str:
    if is_crypto(ticker):
        return "open_24_7"
    now = (now or datetime.now(UTC)).astimezone(ET)
    if now.weekday() >= 5:
        return "closed"
    minutes = now.hour * 60 + now.minute
    if minutes < 4 * 60:
        return "closed"
    if minutes < 9 * 60 + 30:
        return "premarket"
    if minutes < 10 * 60 + 30:
        return "opening_drive"
    if minutes < 12 * 60:
        return "morning"
    if minutes < 14 * 60:
        return "lunch"
    if minutes < 15 * 60:
        return "afternoon"
    if minutes < 16 * 60:
        return "power_hour"
    return "after_hours"


@dataclass(slots=True)
class IntradaySnapshot:
    as_of: str
    close: float
    session: str
    session_note: str
    # Today's structure
    vwap: float | None = None
    vwap_dist_pct: float | None = None  # close vs VWAP; >0 above
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    or_high: float | None = None  # opening range (first 30 min)
    or_low: float | None = None
    # Prior-day context
    prev_close: float | None = None
    prev_high: float | None = None
    prev_low: float | None = None
    gap_pct: float | None = None  # today's open vs prior close
    # Momentum (5-minute bars)
    ema9: float | None = None
    ema20: float | None = None
    rsi14_5m: float | None = None
    macd_hist_5m: float | None = None
    atr_5m: float | None = None  # absolute $, for stops/targets
    atr_pct: float | None = None
    rel_volume: float | None = None  # today vs prior days, same time-of-day
    data_age_minutes: float | None = None


def _day_key(bar: PriceBar, crypto: bool) -> str:
    dt = parse_bar_time(bar.time)
    local = dt if crypto else dt.astimezone(ET)
    return local.date().isoformat()


def split_days(bars: list[PriceBar], crypto: bool) -> list[list[PriceBar]]:
    """Group bars into chronological trading days (ET for stocks, UTC for crypto)."""
    days: list[list[PriceBar]] = []
    current_key: str | None = None
    for bar in bars:
        key = _day_key(bar, crypto)
        if key != current_key:
            days.append([])
            current_key = key
        days[-1].append(bar)
    return days


def vwap(bars: list[PriceBar]) -> float | None:
    num = 0.0
    den = 0.0
    for b in bars:
        vol = b.volume or 0
        if vol <= 0:
            continue
        num += (b.high + b.low + b.close) / 3 * vol
        den += vol
    return round(num / den, 4) if den > 0 else None


def atr(bars: list[PriceBar], period: int = 14) -> float | None:
    if len(bars) < 2:
        return None
    trs: list[float] = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - prev_close),
            abs(bars[i].low - prev_close),
        )
        trs.append(tr)
    window = trs[-period:] if len(trs) >= period else trs
    return round(sum(window) / len(window), 4)


def opening_range(today: list[PriceBar], minutes: int = 30) -> tuple[float | None, float | None]:
    """High/low of the first `minutes` of the session."""
    if not today:
        return None, None
    start = parse_bar_time(today[0].time)
    window = [b for b in today if (parse_bar_time(b.time) - start).total_seconds() < minutes * 60]
    if not window:
        return None, None
    return round(max(b.high for b in window), 4), round(min(b.low for b in window), 4)


def relative_volume(days: list[list[PriceBar]]) -> float | None:
    """Today's cumulative volume vs prior days at the same bar count."""
    if len(days) < 2:
        return None
    today = days[-1]
    n = len(today)
    today_vol = sum(b.volume or 0 for b in today)
    if today_vol <= 0:
        return None
    prior = [sum(b.volume or 0 for b in day[:n]) for day in days[:-1]]
    prior = [p for p in prior if p > 0]
    if not prior:
        return None
    return round(today_vol / (sum(prior) / len(prior)), 2)


def compute_intraday_snapshot(
    ticker: str,
    bars_5m: list[PriceBar],
    now: datetime | None = None,
) -> IntradaySnapshot:
    """Build the desk's deterministic snapshot from ~5 days of 5-minute bars."""
    if not bars_5m:
        raise ValueError("no intraday bars")

    crypto = is_crypto(ticker)
    days = split_days(bars_5m, crypto)
    today = days[-1]
    last = today[-1]
    close = last.close
    phase = session_phase(ticker, now)

    snap = IntradaySnapshot(
        as_of=last.time,
        close=round(close, 4),
        session=phase,
        session_note=SESSION_NOTES[phase],
    )

    snap.vwap = vwap(today)
    if snap.vwap:
        snap.vwap_dist_pct = round((close - snap.vwap) / snap.vwap * 100, 2)
    snap.day_open = round(today[0].open, 4)
    snap.day_high = round(max(b.high for b in today), 4)
    snap.day_low = round(min(b.low for b in today), 4)
    snap.or_high, snap.or_low = opening_range(today)

    if len(days) >= 2:
        prev = days[-2]
        snap.prev_close = round(prev[-1].close, 4)
        snap.prev_high = round(max(b.high for b in prev), 4)
        snap.prev_low = round(min(b.low for b in prev), 4)
        if snap.prev_close > 0:
            snap.gap_pct = round((snap.day_open - snap.prev_close) / snap.prev_close * 100, 2)

    closes = [b.close for b in bars_5m]
    ema9 = _ema(closes, 9)[-1]
    ema20 = _ema(closes, 20)[-1]
    snap.ema9 = round(ema9, 4) if ema9 is not None else None
    snap.ema20 = round(ema20, 4) if ema20 is not None else None
    snap.rsi14_5m = _rsi(closes)
    snap.macd_hist_5m = _macd_hist(closes)
    snap.atr_5m = atr(bars_5m)
    if snap.atr_5m and close > 0:
        snap.atr_pct = round(snap.atr_5m / close * 100, 2)
    snap.rel_volume = relative_volume(days)

    reference = now or datetime.now(UTC)
    snap.data_age_minutes = round(
        max(0.0, (reference - parse_bar_time(last.time)).total_seconds() / 60), 1
    )
    return snap
