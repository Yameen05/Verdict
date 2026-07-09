"""Tests for the technicals snapshot and the timing agent (rules path)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.routers import market as market_mod
from app.services import timing as timing_mod
from app.services.metrics_client import PriceBar
from app.services.technicals import compute_snapshot
from app.services.timing import ACTION_LABELS, TimingAssessment, assess_timing


def _series(closes: list[float]) -> list[PriceBar]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    for i, c in enumerate(closes):
        day = start + timedelta(days=i)
        bars.append(
            PriceBar(
                time=day.isoformat(),
                open=c,
                high=c * 1.01,
                low=c * 0.99,
                close=c,
                volume=1_000_000,
            )
        )
    return bars


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    market_mod._reset_cache()
    monkeypatch.setattr(timing_mod, "_best_effort_headlines", _no_headlines)
    yield
    market_mod._reset_cache()


async def _no_headlines(_ticker):
    return []


def test_snapshot_uptrend_detected():
    # A straight-up series is an uptrend, but also overbought and at its high —
    # so the bias nets to neutral, not bullish. That's intended, honest behavior.
    snap = compute_snapshot(_series([100 + i for i in range(60)]))
    assert snap.trend == "up"
    assert snap.bias in {"bullish", "neutral"}
    assert snap.sma50 is not None
    assert snap.rsi14 is not None and snap.rsi14 > 60
    assert snap.close == 159.0
    assert any("50-day" in s for s in snap.signals)


def test_snapshot_downtrend_is_bearish():
    snap = compute_snapshot(_series([200 - i for i in range(60)]))
    assert snap.trend == "down"
    assert snap.bias == "bearish"


async def test_assess_timing_rules_buy_on_uptrend(monkeypatch):
    bars = _series([100 + i for i in range(60)])
    monkeypatch.setattr(timing_mod, "fetch_price_history", lambda *_a, **_k: (bars, "1D"))
    monkeypatch.setattr(timing_mod, "fetch_days_to_earnings", lambda *_a, **_k: None)
    res = await assess_timing("AAPL", 14)
    assert res.source == "rules"  # no LLM key configured in tests
    assert res.action in {"buy_now", "accumulate"}
    assert res.action_label == ACTION_LABELS[res.action]
    assert 0 <= res.confidence <= 80
    assert res.rationale
    assert res.risks
    assert res.disclaimer


async def test_assess_timing_avoids_on_downtrend(monkeypatch):
    bars = _series([200 - i for i in range(60)])
    monkeypatch.setattr(timing_mod, "fetch_price_history", lambda *_a, **_k: (bars, "1D"))
    monkeypatch.setattr(timing_mod, "fetch_days_to_earnings", lambda *_a, **_k: None)
    res = await assess_timing("AAPL", 30)
    assert res.action in {"avoid", "wait_watch"}


async def test_earnings_imminent_adds_risk_and_defers_buy(monkeypatch):
    bars = _series([100 + i for i in range(60)])
    monkeypatch.setattr(timing_mod, "fetch_price_history", lambda *_a, **_k: (bars, "1D"))
    monkeypatch.setattr(timing_mod, "fetch_days_to_earnings", lambda *_a, **_k: 2)
    res = await assess_timing("AAPL", 14)
    # A would-be buy/accumulate defers when earnings are 2 days out.
    assert res.action == "wait_watch"
    assert any("arnings" in r for r in res.risks)


def test_snapshot_has_macd_and_ma_trend():
    snap = compute_snapshot(_series([100 + i * 0.5 for i in range(220)]))
    assert snap.macd_hist is not None
    assert snap.ma_trend == "golden"  # rising series → 50-day above 200-day
    assert any("MACD" in s for s in snap.signals)


async def test_timing_endpoint(client, monkeypatch):
    canned = TimingAssessment(
        ticker="AAPL",
        horizon_days=14,
        action="buy_now",
        action_label="Buy now",
        confidence=70,
        summary="Setup favors an entry.",
        rationale=["above 50-day average"],
        risks=["could reverse on news"],
        technicals={},
        as_of="2026-07-09T00:00:00Z",
        source="rules",
    )

    async def fake_assess(ticker, horizon):
        assert ticker == "AAPL"
        assert horizon == 14
        return canned

    monkeypatch.setattr(market_mod, "assess_timing", fake_assess)
    res = client.get("/market/aapl/timing?horizon=14")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["action"] == "buy_now"
    assert body["confidence"] == 70
    assert "not financial advice" in body["disclaimer"].lower()
