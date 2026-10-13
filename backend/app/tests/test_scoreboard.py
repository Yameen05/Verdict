"""Deadline gating, frozen horizon results, rich details, and background grading."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.persistence.db import ResearchRun, get_sessionmaker, save_run
from app.routers import scoreboard as scoreboard_mod
from app.services import track_record
from app.services.backtest import compute_backtest
from app.services.metrics_client import PriceBar

NOW = datetime(2026, 10, 10, 18, 0, tzinfo=UTC)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def isolated_prices_and_clock(monkeypatch):
    track_record._history_cache.clear()
    monkeypatch.setattr(scoreboard_mod, "datetime", Clock)
    monkeypatch.setattr(track_record, "datetime", Clock)

    async def no_prices(_ticker):
        return []

    monkeypatch.setattr(track_record, "daily_history", no_prices)
    yield
    track_record._history_cache.clear()


def bar(ends_at, price):
    return PriceBar(time=(ends_at - timedelta(days=1)).isoformat(), open=price,
                    high=price, low=price, close=price, volume=1000)


async def seed(ticker="NVDA", rec="Buy", price=100.0, *, days=7, created=None, payload=None):
    async with get_sessionmaker()() as session:
        row = await save_run(
            session, ticker=ticker, recommendation=rec, justification="Original reasoning",
            sentiment_score=None, confidence=70, horizon_days=days,
            price_at_run=price, payload=payload or {}, duration_ms=1500, cost_usd=0.01,
            llm_model="original-model",
        )
        row.created_at = created or NOW
        await session.commit()
        return row.id


async def test_new_analysis_is_open_until_exact_deadline(client, monkeypatch):
    created = NOW - timedelta(days=7) + timedelta(seconds=1)
    await seed(created=created)

    async def unexpected_price(_ticker):
        pytest.fail("A future call must not fetch a grading price")

    monkeypatch.setattr(track_record, "daily_history", unexpected_price)
    body = client.get("/research/scoreboard").json()
    entry = body["entries"][0]
    assert entry["outcome"] == "in_progress"
    assert datetime.fromisoformat(entry["due_at"]) == NOW + timedelta(seconds=1)
    assert entry["price_at_horizon"] is None
    assert entry["return_pct"] is None
    assert body["summary"]["scored"] == 0
    assert body["summary"]["hit_rate"] is None
    assert body["summary"]["in_progress"] == 1


@pytest.mark.parametrize("days", [7, 14, 30, 90, 365])
async def test_each_holding_period_keeps_original_time(client, days):
    await seed(days=days)
    body = client.get("/research/scoreboard").json()
    entry = body["entries"][0]
    assert datetime.fromisoformat(entry["due_at"]) == NOW + timedelta(days=days)
    assert entry["outcome"] == "in_progress"


async def test_scoreboard_grades_horizon_price_and_freezes_it(client, monkeypatch):
    deadline = NOW - timedelta(days=1)
    await seed(created=deadline - timedelta(days=7))

    async def prices(_ticker):
        return [bar(deadline, 110), bar(NOW, 50)]

    monkeypatch.setattr(track_record, "daily_history", prices)
    body = client.get("/research/scoreboard").json()
    entry = body["entries"][0]
    assert entry["outcome"] == "hit"
    assert entry["price_at_horizon"] == 110
    assert entry["return_pct"] == 10
    assert body["summary"]["hit_rate"] == 1

    async def changed_prices(_ticker):
        pytest.fail("Finalized results must not fetch or use newer prices")

    monkeypatch.setattr(track_record, "daily_history", changed_prices)
    later = client.get("/research/scoreboard").json()["entries"][0]
    assert later == entry
    async with get_sessionmaker()() as session:
        row = await session.scalar(select(ResearchRun))
        assert row.horizon_evaluation["outcome"] == "hit"
        assert compute_backtest([row], {"NVDA": [bar(NOW, 50)]}, now=NOW).entries[0].outcome == "hit"


@pytest.mark.parametrize("recommendation,price,outcome", [
    ("Buy", 100, "miss"), ("Buy", 110, "hit"),
    ("Sell", 90, "hit"), ("Sell", 110, "miss"),
    ("Hold", 105, "hit"), ("Hold", 106, "miss"),
])
async def test_exact_deadline_grading_rules(client, monkeypatch, recommendation, price, outcome):
    await seed(rec=recommendation, created=NOW - timedelta(days=7))

    async def prices(_ticker):
        return [bar(NOW, price)]

    monkeypatch.setattr(track_record, "daily_history", prices)
    entry = client.get("/research/scoreboard").json()["entries"][0]
    assert entry["outcome"] == outcome


async def test_incomplete_daily_candle_waits_even_after_deadline(client, monkeypatch):
    await seed(created=NOW - timedelta(days=7, hours=1))

    async def prices(_ticker):
        return [bar(NOW + timedelta(hours=5), 110)]

    monkeypatch.setattr(track_record, "daily_history", prices)
    body = client.get("/research/scoreboard").json()
    assert body["entries"][0]["outcome"] == "awaiting_price"
    assert body["entries"][0]["return_pct"] is None
    assert body["summary"]["awaiting_price"] == 1
    assert body["summary"]["scored"] == 0


async def test_market_closure_waits_then_uses_next_completed_candle(client, monkeypatch):
    deadline = NOW - timedelta(days=2)
    await seed(created=deadline - timedelta(days=7))
    calls = 0

    async def prices(_ticker):
        nonlocal calls
        calls += 1
        return [bar(deadline - timedelta(days=1), 90)] if calls == 1 else [bar(NOW, 110)]

    monkeypatch.setattr(track_record, "daily_history", prices)
    assert client.get("/research/scoreboard").json()["entries"][0]["outcome"] == "awaiting_price"
    assert client.get("/research/scoreboard").json()["entries"][0]["outcome"] == "hit"


async def test_unscorable_calls_and_legacy_horizon_are_explicit(client):
    await seed(ticker="AAPL", rec="Pending", created=NOW - timedelta(days=20))
    await seed(ticker="MSFT", price=None, created=NOW - timedelta(days=20))
    await seed(ticker="AMZN", days=None)
    body = client.get("/research/scoreboard").json()
    entries = {e["ticker"]: e for e in body["entries"]}
    assert entries["AAPL"]["outcome"] == "failed"
    assert entries["MSFT"]["outcome"] == "unscored"
    assert entries["AMZN"]["horizon_days"] is None
    assert entries["AMZN"]["due_at"] is None
    assert entries["AMZN"]["outcome"] == "unscored"
    assert entries["AMZN"]["horizon_assumed"] is False
    assert body["summary"]["unscored"] == 2
    assert body["summary"]["hit_rate"] is None


async def test_details_return_full_original_snapshot_and_missing_run(client):
    payload = {
        "ticker": "NVDA", "sec": {"status": "skipped"}, "news": {"status": "ok"},
        "metrics": {"status": "ok", "current_price": 100},
        "report": {"ticker": "NVDA", "recommendation": "Buy", "justification": "Original reasoning",
                   "company_overview": "Nvidia", "financial_health": "Saved financials", "horizon_days": 7},
        "evidence": [{"id": "metrics:price", "source": "metrics", "label": "Issue price", "content": "$100"}],
    }
    run_id = await seed(payload=payload)
    res = client.get(f"/research/scoreboard/{run_id}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["payload"] == payload
    assert body["result"]["evidence"][0]["content"] == "$100"
    assert body["entry"]["model"] == "original-model"
    assert body["entry"]["outcome"] == "in_progress"
    assert body["cost_usd"] == 0.01
    assert client.get("/research/scoreboard/9999").status_code == 404
    client.cookies.clear()
    assert client.get(f"/research/scoreboard/{run_id}").status_code == 401


async def test_details_preserve_incomplete_legacy_payload(client):
    run_id = await seed(payload={"old": "all original fields"})
    body = client.get(f"/research/scoreboard/{run_id}").json()
    assert body["result"] is None
    assert body["payload"] == {"old": "all original fields"}
    assert body["justification"] == "Original reasoning"


async def test_background_grading_handles_more_than_one_batch(client, monkeypatch):
    for i in range(track_record.MAX_TICKERS + 1):
        await seed(ticker=f"T{i}", created=NOW - timedelta(days=8))
    await seed(ticker="FUTURE", created=NOW)

    async def prices(ticker):
        assert ticker != "FUTURE"
        return [bar(NOW - timedelta(days=1), 110)]

    monkeypatch.setattr(track_record, "daily_history", prices)
    async with get_sessionmaker()() as session:
        assert await track_record.evaluate_due_once(session) == track_record.MAX_TICKERS + 1
        assert await track_record.evaluate_due_once(session) == 0


async def test_empty_scoreboard(client):
    body = client.get("/research/scoreboard").json()
    assert body["entries"] == []
    assert body["summary"]["hit_rate"] is None
