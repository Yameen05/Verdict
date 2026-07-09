"""Tests for the horizon-aware backtest (services/backtest + /market/backtest)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.routers import market as market_mod
from app.services.backtest import compute_backtest
from app.services.metrics_client import PriceBar

NOW = datetime(2026, 7, 9, tzinfo=UTC)


@dataclass
class FakeRun:
    id: int
    ticker: str
    recommendation: str
    horizon_days: int | None
    price_at_run: float | None
    created_at: datetime
    confidence: int | None = 70


def _daily(start: datetime, closes: list[float]) -> list[PriceBar]:
    bars = []
    for i, close in enumerate(closes):
        day = start + timedelta(days=i)
        bars.append(
            PriceBar(
                time=day.isoformat(),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1000,
            )
        )
    return bars


def test_compute_scores_buy_at_horizon():
    created = NOW - timedelta(days=30)
    run = FakeRun(1, "AAPL", "Buy", 14, 100.0, created)
    # Daily history rising from 100 -> 120 over the window; horizon lands on +14d.
    history = _daily(created, [100.0 + i for i in range(31)])
    res = compute_backtest([run], {"AAPL": history}, now=NOW)

    entry = res.entries[0]
    assert entry.outcome == "hit"
    assert entry.price_at_horizon == pytest.approx(114.0)
    assert entry.return_pct == pytest.approx(14.0)
    assert res.summary.scored == 1
    assert res.summary.hits == 1
    assert res.summary.hit_rate == pytest.approx(1.0)
    assert res.summary.by_horizon[0].horizon_days == 14


def test_compute_marks_immature_when_horizon_not_elapsed():
    created = NOW - timedelta(days=3)
    run = FakeRun(2, "MSFT", "Buy", 30, 200.0, created)
    res = compute_backtest([run], {"MSFT": []}, now=NOW)

    assert res.entries[0].outcome == "immature"
    assert res.summary.immature == 1
    assert res.summary.scored == 0
    assert res.summary.hit_rate is None


def test_compute_sell_and_hold_rules():
    created = NOW - timedelta(days=40)
    sell = FakeRun(3, "NVDA", "Sell", 14, 100.0, created)  # falls -> hit
    hold = FakeRun(4, "TSLA", "Hold", 14, 100.0, created)  # flat -> hit
    hist_down = _daily(created, [100.0 - i * 0.5 for i in range(41)])
    hist_flat = _daily(created, [100.0 + (i % 2) * 0.2 for i in range(41)])
    res = compute_backtest(
        [sell, hold], {"NVDA": hist_down, "TSLA": hist_flat}, now=NOW
    )
    by_id = {e.id: e for e in res.entries}
    assert by_id[3].outcome == "hit"
    assert by_id[4].outcome == "hit"
    assert res.summary.scored == 2
    assert res.summary.hits == 2


def test_compute_skips_pending_and_priceless():
    created = NOW - timedelta(days=40)
    res = compute_backtest(
        [
            FakeRun(5, "AAPL", "Pending", 14, 100.0, created),
            FakeRun(6, "AAPL", "Buy", 14, None, created),
        ],
        {"AAPL": _daily(created, [100.0] * 41)},
        now=NOW,
    )
    assert res.summary.scored == 0
    assert all(e.outcome == "unscored" for e in res.entries)


async def test_backtest_endpoint(client, monkeypatch):
    created = NOW - timedelta(days=30)

    async def fake_recent(_session, limit=200):
        return [FakeRun(1, "AAPL", "Buy", 14, 100.0, created)]

    async def fake_daily(ticker: str):
        assert ticker == "AAPL"
        return _daily(created, [100.0 + i for i in range(31)])

    monkeypatch.setattr(market_mod, "list_recent_runs", fake_recent)
    monkeypatch.setattr(market_mod, "_daily_history", fake_daily)

    res = client.get("/market/backtest")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["summary"]["scored"] == 1
    assert body["summary"]["hits"] == 1
    assert body["entries"][0]["outcome"] == "hit"
