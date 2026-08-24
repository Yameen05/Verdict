"""Rate limits must bind per endpoint, not per URL.

Both routes here spend real LLM budget per cache miss, and the ticker is in the
path — so a limiter bucket that includes the path would never bind.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.limiter import limiter

BOOTSTRAP_TOKEN = "test-bootstrap-token-with-at-least-32-characters"


@pytest.fixture
def capped_client(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_DAYTRADE", "3/minute")
    monkeypatch.setenv("RATE_LIMIT_RESEARCH", "3/minute")
    get_settings.cache_clear()
    limiter.reset()

    from app.main import create_app

    with TestClient(create_app()) as client:
        created = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json={"email": "owner@example.com", "password": "a-strong-test-password-123"},
        )
        assert created.status_code == 201, created.text
        client.headers.update({"X-CSRF-Token": created.json()["csrf_token"]})
        yield client
    limiter.reset()


def test_signal_limit_binds_across_different_tickers(capped_client, monkeypatch):
    from app.routers import daytrade

    calls = {"n": 0}

    async def counting_assess(ticker):
        calls["n"] += 1
        raise daytrade.DayTradeError("no intraday data")

    monkeypatch.setattr(daytrade, "assess_daytrade", counting_assess)

    statuses = [capped_client.get(f"/daytrade/TEST{n}/signal").status_code for n in range(6)]

    assert 429 in statuses, statuses
    # The limiter absorbed the excess before any further LLM work was reached.
    assert calls["n"] <= 3, calls


def test_scan_endpoint_is_rate_limited(capped_client, monkeypatch):
    from app.routers import daytrade

    async def failing_scan():
        raise daytrade.DayTradeError("no data")

    monkeypatch.setattr(daytrade, "scan_daytrade", failing_scan)
    statuses = [capped_client.get("/daytrade/scan").status_code for _ in range(6)]
    assert 429 in statuses, statuses


def test_research_limit_binds_across_different_tickers(capped_client, monkeypatch):
    """A per-URL bucket would give one fresh 30/minute allowance per symbol."""
    from app.routers import research

    async def instant_cache_miss(session, ticker, horizon_days):
        return None

    async def refuse(*args, **kwargs):
        raise AssertionError("pipeline should not run in this test")

    monkeypatch.setattr(research, "_cached_run", instant_cache_miss)
    monkeypatch.setattr(research, "_enforce_quota", refuse)

    statuses = [capped_client.post(f"/research/TEST{n}").status_code for n in range(6)]
    assert 429 in statuses, statuses
