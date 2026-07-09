"""Shared run cache and daily quota enforcement."""

from __future__ import annotations

import json

from app.config import get_settings
from app.persistence.db import save_run, session_scope
from app.schemas.research import (
    InsiderFindings,
    MetricsFindings,
    NewsFindings,
    ResearchReport,
    ResearchResponse,
    SECFindings,
)


def _payload(ticker: str = "AAPL") -> dict:
    return ResearchResponse(
        ticker=ticker,
        sec=SECFindings(status="skipped"),
        news=NewsFindings(status="skipped"),
        metrics=MetricsFindings(status="ok", current_price=100.0),
        insider=InsiderFindings(status="skipped"),
        report=ResearchReport(
            ticker=ticker,
            recommendation="Buy",
            justification="cached-run",
            company_overview="",
            financial_health="",
            confidence=70,
        ),
    ).model_dump()


async def _seed_run(ticker: str, user_id: int | None) -> None:
    async for session in session_scope():
        await save_run(
            session,
            user_id=user_id,
            ticker=ticker,
            recommendation="Buy",
            justification="cached-run",
            sentiment_score=None,
            confidence=70,
            price_at_run=100.0,
            horizon_days=14,
            payload=_payload(ticker),
        )
        break


def _user_id(client) -> int:
    return client.get("/auth/me").json()["user"]["id"]


async def test_recent_run_served_from_cache(client):
    await _seed_run("AAPL", _user_id(client))
    res = client.post("/research/AAPL")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cached"] is True
    assert body["cache_age_minutes"] is not None
    assert body["result"]["report"]["justification"] == "cached-run"


async def test_stream_serves_cache_as_completed_event(client):
    await _seed_run("AAPL", _user_id(client))
    with client.stream("GET", "/research/AAPL/stream") as res:
        assert res.status_code == 200
        raw = "".join(chunk for chunk in res.iter_text())
    assert "event: completed" in raw
    completed = json.loads(raw.split("event: completed")[1].split("data: ")[1].split("\n")[0])
    assert completed["cached"] is True
    assert completed["result"]["report"]["recommendation"] == "Buy"


async def test_fresh_flag_bypasses_cache(client, monkeypatch):
    await _seed_run("AAPL", _user_id(client))

    async def fake_run_research(ticker, prior_run=None, horizon_days=14):
        assert prior_run is not None  # prior run reached the pipeline
        return ResearchResponse(**_payload(ticker))

    async def no_ingest(_ticker):
        return False

    import app.routers.research as research_mod

    monkeypatch.setattr(research_mod, "run_research", fake_run_research)
    monkeypatch.setattr(research_mod, "_needs_auto_ingest", no_ingest)
    res = client.post("/research/AAPL?fresh=true")
    assert res.status_code == 200, res.text
    assert res.json()["cached"] is False


async def test_per_user_daily_quota(client, monkeypatch):
    monkeypatch.setenv("DAILY_RUNS_PER_USER", "2")
    monkeypatch.setenv("RESEARCH_CACHE_MINUTES", "0")  # force fresh runs
    get_settings.cache_clear()

    uid = _user_id(client)
    await _seed_run("AAPL", uid)
    await _seed_run("MSFT", uid)

    res = client.post("/research/NVDA")
    assert res.status_code == 429
    assert "fresh runs" in res.json()["detail"]
    get_settings.cache_clear()


async def test_global_daily_quota(client, monkeypatch):
    monkeypatch.setenv("DAILY_RUNS_GLOBAL", "1")
    monkeypatch.setenv("RESEARCH_CACHE_MINUTES", "0")
    get_settings.cache_clear()

    # A run by ANOTHER user consumes the global budget (user_id=None keeps
    # the FK happy while still counting toward the global total).
    await _seed_run("AAPL", None)

    res = client.post("/research/NVDA")
    assert res.status_code == 429
    assert "community" in res.json()["detail"]
    get_settings.cache_clear()


async def test_cache_disabled_when_ttl_zero(client, monkeypatch):
    monkeypatch.setenv("RESEARCH_CACHE_MINUTES", "0")
    get_settings.cache_clear()
    await _seed_run("AAPL", _user_id(client))

    async def fake_run_research(ticker, prior_run=None, horizon_days=14):
        return ResearchResponse(**_payload(ticker))

    async def no_ingest(_ticker):
        return False

    import app.routers.research as research_mod

    monkeypatch.setattr(research_mod, "run_research", fake_run_research)
    monkeypatch.setattr(research_mod, "_needs_auto_ingest", no_ingest)
    res = client.post("/research/AAPL")
    assert res.status_code == 200
    assert res.json()["cached"] is False
    get_settings.cache_clear()


async def test_needs_auto_ingest_uses_active_vectorstore(monkeypatch):
    import app.routers.research as research_mod
    from app.services import vectorstore as vectorstore_mod

    seen: list[str] = []

    async def fake_has_chunks(ticker: str) -> bool:
        seen.append(ticker)
        return False

    monkeypatch.setattr(vectorstore_mod, "has_chunks", fake_has_chunks)

    assert await research_mod._needs_auto_ingest("NVDA") is True
    assert seen == ["NVDA"]
