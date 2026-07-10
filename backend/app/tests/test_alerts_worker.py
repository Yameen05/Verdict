"""Tests for the background alert/verdict-watch evaluator."""

from __future__ import annotations

import asyncio

from app.services import alerts_worker as worker_mod
from app.services.metrics_client import MetricsClientError, PriceBar


def _bar(close: float) -> tuple[PriceBar, str]:
    return (
        PriceBar(
            time="2026-07-09T15:30:00Z",
            open=close,
            high=close,
            low=close,
            close=close,
        ),
        "1M",
    )


def _run_with_fresh_session(coro_factory):
    """Run a worker coroutine on its own loop with a fresh engine.

    TestClient's app loop owns the global aiosqlite engine; reusing it from
    asyncio.run() would cross event loops. Reset before AND after so each side
    gets an engine bound to its own loop, pointed at the same SQLite file.
    """
    from app.persistence import db as db_mod

    db_mod._engine = None
    db_mod._sessionmaker = None

    async def runner():
        async with db_mod.get_sessionmaker()() as session:
            return await coro_factory(session)

    try:
        return asyncio.run(runner())
    finally:
        db_mod._engine = None
        db_mod._sessionmaker = None


def test_worker_triggers_crossed_alerts(client, monkeypatch):
    client.post("/me/alerts", json={"ticker": "AAPL", "direction": "above", "price": 100})
    client.post("/me/alerts", json={"ticker": "AAPL", "direction": "below", "price": 90})
    monkeypatch.setattr(worker_mod, "fetch_latest_price_bar", lambda t, i="1M": _bar(105.0))

    triggered = _run_with_fresh_session(worker_mod.evaluate_alerts_once)
    assert triggered == 1

    alerts = {a["direction"]: a for a in client.get("/me/alerts").json()["alerts"]}
    assert alerts["above"]["triggered"] is True
    assert alerts["above"]["triggered_price"] == 105.0
    assert alerts["below"]["triggered"] is False

    # A second pass does not re-trigger.
    assert _run_with_fresh_session(worker_mod.evaluate_alerts_once) == 0


def test_worker_survives_provider_failure(client, monkeypatch):
    client.post("/me/alerts", json={"ticker": "AAPL", "direction": "above", "price": 100})

    def boom(_ticker, _interval="1M"):
        raise MetricsClientError("provider down")

    monkeypatch.setattr(worker_mod, "fetch_latest_price_bar", boom)
    assert _run_with_fresh_session(worker_mod.evaluate_alerts_once) == 0
    alerts = client.get("/me/alerts").json()["alerts"]
    assert alerts[0]["triggered"] is False


def test_worker_emails_on_trigger(client, monkeypatch):
    client.post("/me/alerts", json={"ticker": "AAPL", "direction": "above", "price": 100})
    monkeypatch.setattr(worker_mod, "fetch_latest_price_bar", lambda t, i="1M": _bar(101.0))
    monkeypatch.setattr(worker_mod, "email_configured", lambda: True)
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        worker_mod, "send_email", lambda to, subject, body: sent.append((to, subject)) or True
    )

    assert _run_with_fresh_session(worker_mod.evaluate_alerts_once) == 1
    assert sent == [("owner@example.com", "Verdict price alert: AAPL")]


def test_worker_notifies_verdict_watch_change(client, monkeypatch):
    # Arm a watch for Buy, then store a newer run that says Sell.
    client.post("/me/verdict-watch", json={"ticker": "AAPL", "recommendation": "Buy"})

    from app.persistence.db import save_run

    async def seed(session):
        await save_run(
            session,
            ticker="AAPL",
            recommendation="Sell",
            justification="test",
            sentiment_score=None,
            payload={},
        )
        return await worker_mod.evaluate_verdict_watches_once(session)

    changed = _run_with_fresh_session(seed)
    assert changed == 1
    # Watch re-armed at the new recommendation: no repeat notification.
    assert client.get("/me/verdict-watch/AAPL").json() == {"recommendation": "Sell"}
    assert _run_with_fresh_session(worker_mod.evaluate_verdict_watches_once) == 0
