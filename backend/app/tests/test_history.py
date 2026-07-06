"""Tests for the research-history persistence layer."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.persistence.db import (
    init_db,
    list_runs_for_ticker,
    save_run,
    session_scope,
)


@asynccontextmanager
async def _open_session():
    async for s in session_scope():
        yield s
        return
    raise RuntimeError("no session")


async def test_save_and_list_runs():
    await init_db()
    async with _open_session() as session:
        run = await save_run(
            session,
            ticker="AAPL",
            recommendation="Buy",
            justification="Strong fundamentals.",
            sentiment_score=0.3,
            payload={"foo": "bar"},
            duration_ms=1234.5,
            cost_usd=0.0021,
            request_id="rid-1",
        )
        assert run.id is not None
        assert run.ticker == "AAPL"

    async with _open_session() as session:
        rows = await list_runs_for_ticker(session, "AAPL")
        assert len(rows) == 1
        assert rows[0].recommendation == "Buy"
        assert rows[0].cost_usd == pytest.approx(0.0021)


async def test_history_endpoint_returns_runs(client):
    # No runs yet → empty list
    res = client.get("/research/history/AAPL")
    assert res.status_code == 200
    assert res.json() == {"ticker": "AAPL", "runs": []}


async def test_history_rejects_bad_ticker(client):
    res = client.get("/research/history/!!!")
    assert res.status_code == 400
