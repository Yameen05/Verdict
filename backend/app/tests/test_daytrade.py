"""Tests for the day-trade desk: intraday math, agents, and risk discipline."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.daytrade import rules_signal, run_desk
from app.services.daytrade_intraday import (
    compute_intraday_snapshot,
    opening_range,
    relative_volume,
    session_phase,
    split_days,
    vwap,
)
from app.services.metrics_client import PriceBar

ET = ZoneInfo("America/New_York")


def bar(t: datetime, o: float, h: float, low: float, c: float, v: int = 10_000) -> PriceBar:
    return PriceBar(
        time=t.isoformat(), open=round(o, 4), high=round(h, 4), low=round(low, 4),
        close=round(c, 4), volume=v,
    )


def session_bars(
    day: datetime,
    start_price: float,
    drift_per_bar: float,
    n_bars: int = 78,
    volume: int = 10_000,
    wiggle: float = 0.05,
) -> list[PriceBar]:
    """One session of 5-minute bars starting 09:30 ET, drifting steadily."""
    bars: list[PriceBar] = []
    t0 = day.replace(hour=9, minute=30, tzinfo=ET)
    price = start_price
    for i in range(n_bars):
        o = price
        c = price + drift_per_bar
        h = max(o, c) + wiggle
        low = min(o, c) - wiggle
        bars.append(bar(t0 + timedelta(minutes=5 * i), o, h, low, c, volume))
        price = c
    return bars


def multi_day(days: int, start: float, drift: float, today_drift: float, today_vol: int = 10_000) -> list[PriceBar]:
    """`days-1` flat context days then one trending 'today'."""
    out: list[PriceBar] = []
    base = datetime(2026, 7, 6)  # a Monday
    price = start
    for d in range(days - 1):
        day_bars = session_bars(base + timedelta(days=d), price, drift)
        out.extend(day_bars)
        price = day_bars[-1].close
    out.extend(session_bars(base + timedelta(days=days - 1), price, today_drift, volume=today_vol))
    return out


MIDDAY = datetime(2026, 7, 10, 10, 45, tzinfo=ET)  # Friday mid-morning


# ------------------------------------------------------------- intraday math


def test_vwap_weighs_by_volume() -> None:
    t = datetime(2026, 7, 10, 9, 30, tzinfo=ET)
    bars = [
        bar(t, 10, 10, 10, 10, v=100),        # typical price 10
        bar(t + timedelta(minutes=5), 20, 20, 20, 20, v=300),  # typical price 20
    ]
    assert vwap(bars) == pytest.approx(17.5)


def test_opening_range_uses_first_30_minutes() -> None:
    bars = session_bars(datetime(2026, 7, 10), 100, 0.5)
    or_high, or_low = opening_range(bars)
    first_six = bars[:6]  # 30 minutes of 5m bars
    assert or_high == pytest.approx(max(b.high for b in first_six))
    assert or_low == pytest.approx(min(b.low for b in first_six))


def test_split_days_groups_et_sessions() -> None:
    bars = multi_day(3, 100, 0.0, 0.1)
    days = split_days(bars, crypto=False)
    assert len(days) == 3
    assert len(days[0]) == 78


def test_relative_volume_compares_same_bar_count() -> None:
    bars = multi_day(3, 100, 0.0, 0.0, today_vol=20_000)
    days = split_days(bars, crypto=False)
    assert relative_volume(days) == pytest.approx(2.0)


def test_session_phase_clock() -> None:
    assert session_phase("BTC-USD", MIDDAY) == "open_24_7"
    assert session_phase("AAPL", MIDDAY) == "morning"
    assert session_phase("AAPL", MIDDAY.replace(hour=12, minute=30)) == "lunch"
    assert session_phase("AAPL", MIDDAY.replace(hour=15, minute=30)) == "power_hour"
    assert session_phase("AAPL", MIDDAY.replace(hour=20, minute=0)) == "after_hours"
    saturday = MIDDAY + timedelta(days=1)
    assert session_phase("AAPL", saturday) == "closed"


# ------------------------------------------------------------------ the desk


def _signal_for(bars: list[PriceBar], ticker: str = "TEST", now: datetime = MIDDAY):
    snap = compute_intraday_snapshot(ticker, bars, now)
    agents = run_desk(snap, [])
    return rules_signal(ticker, snap, agents, []), snap, agents


def test_strong_uptrend_goes_long_with_coherent_plan() -> None:
    bars = multi_day(5, 100, 0.0, 0.15, today_vol=20_000)
    sig, snap, agents = _signal_for(bars)
    assert sig.action == "long"
    assert sig.entry is not None and sig.stop is not None and sig.target is not None
    assert sig.stop < sig.entry < sig.target
    assert sig.risk_reward is not None and sig.risk_reward >= 1.3
    assert sig.confidence <= 80
    assert snap.vwap is not None and snap.close > snap.vwap


def test_strong_downtrend_goes_short_with_coherent_plan() -> None:
    bars = multi_day(5, 100, 0.0, -0.15, today_vol=20_000)
    sig, _, _ = _signal_for(bars)
    assert sig.action == "short"
    assert sig.entry is not None and sig.stop is not None and sig.target is not None
    assert sig.target < sig.entry < sig.stop
    assert sig.risk_reward is not None and sig.risk_reward >= 1.3


def test_choppy_tape_stands_aside() -> None:
    # Alternating up/down bars — no trend, EMAs tangled.
    bars: list[PriceBar] = []
    base = datetime(2026, 7, 6)
    price = 100.0
    for d in range(5):
        t0 = (base + timedelta(days=d)).replace(hour=9, minute=30, tzinfo=ET)
        for i in range(78):
            drift = 0.2 if i % 2 == 0 else -0.2
            o, c = price, price + drift
            bars.append(bar(t0 + timedelta(minutes=5 * i), o, max(o, c) + 0.05, min(o, c) - 0.05, c))
            price = c
    sig, _, _ = _signal_for(bars)
    assert sig.action == "stand_aside"
    assert sig.entry is None and sig.stop is None


def test_closed_market_never_issues_live_entry() -> None:
    bars = multi_day(5, 100, 0.0, 0.15, today_vol=20_000)
    sunday = datetime(2026, 7, 12, 12, 0, tzinfo=ET)
    sig, _, _ = _signal_for(bars, now=sunday)
    assert sig.action == "stand_aside"
    assert any("session" in r.lower() or "open" in r.lower() for r in sig.risks)


def test_crypto_session_is_always_tradable() -> None:
    bars = multi_day(5, 100, 0.0, 0.15, today_vol=20_000)
    sunday = datetime(2026, 7, 12, 12, 0, tzinfo=ET)
    sig, snap, _ = _signal_for(bars, ticker="BTC-USD", now=sunday)
    assert snap.session == "open_24_7"
    assert sig.action == "long"


def test_desk_has_five_named_agents() -> None:
    bars = multi_day(3, 100, 0.0, 0.1)
    _, snap, agents = _signal_for(bars)
    assert [a.name for a in agents] == [
        "Trend", "Momentum", "Volume / VWAP", "Levels", "Catalyst",
    ]
    assert all(a.reasons for a in agents)
