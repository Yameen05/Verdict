"""Tests for the scoreboard endpoint (forward returns + hit rate)."""

from __future__ import annotations

import pytest

from app.persistence.db import save_run, session_scope
from app.routers import scoreboard as scoreboard_mod


@pytest.fixture(autouse=True)
def reset_price_cache():
    scoreboard_mod._reset_price_cache()
    yield
    scoreboard_mod._reset_price_cache()


async def _seed(ticker: str, recommendation: str, price_at_run: float | None, user_id: int):
    async for session in session_scope():
        await save_run(
            session,
            user_id=user_id,
            ticker=ticker,
            recommendation=recommendation,
            justification="seeded",
            sentiment_score=None,
            confidence=70,
            price_at_run=price_at_run,
            payload={},
        )
        break


async def test_scoreboard_scores_and_summarizes(client, monkeypatch):
    user_id = client.get("/auth/me").json()["user"]["id"]

    await _seed("AAPL", "Buy", 100.0, user_id)   # +10% → hit
    await _seed("MSFT", "Sell", 200.0, user_id)  # -5%  → hit
    await _seed("NVDA", "Hold", 50.0, user_id)   # +20% → miss (outside ±5%)
    await _seed("TSLA", "Pending", 10.0, user_id)  # unscored
    await _seed("AMZN", "Buy", None, user_id)      # no price → unscored

    prices = {"AAPL": 110.0, "MSFT": 190.0, "NVDA": 60.0, "TSLA": 11.0, "AMZN": 150.0}
    monkeypatch.setattr(scoreboard_mod, "fetch_price", lambda t: prices[t])

    res = client.get("/research/scoreboard")
    assert res.status_code == 200, res.text
    body = res.json()

    by_ticker = {e["ticker"]: e for e in body["entries"]}
    assert by_ticker["AAPL"]["outcome"] == "hit"
    assert by_ticker["AAPL"]["return_pct"] == pytest.approx(10.0)
    assert by_ticker["MSFT"]["outcome"] == "hit"
    assert by_ticker["NVDA"]["outcome"] == "miss"
    assert by_ticker["TSLA"]["outcome"] == "unscored"
    assert by_ticker["AMZN"]["outcome"] == "unscored"

    s = body["summary"]
    assert s["total_runs"] == 5
    assert s["scored"] == 3
    assert s["hits"] == 2
    assert s["hit_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert s["avg_return_buy_pct"] == pytest.approx(10.0)
    assert "±5" in s["rule"] or "5%" in s["rule"]


async def test_scoreboard_empty(client):
    res = client.get("/research/scoreboard")
    assert res.status_code == 200
    body = res.json()
    assert body["entries"] == []
    assert body["summary"]["hit_rate"] is None
