"""Unit tests for the metrics agent node."""

from __future__ import annotations

import pytest

from app.agents.nodes import metrics_agent as metrics_agent_mod
from app.schemas.research import MetricsFindings
from app.services.metrics_client import Metrics, MetricsClientError


@pytest.fixture(autouse=True)
def reset_cache():
    metrics_agent_mod._reset_cache()
    yield
    metrics_agent_mod._reset_cache()


async def test_metrics_agent_happy_path(monkeypatch):
    def fake_fetch(_ticker):
        return Metrics(
            revenue=1.0e11,
            eps=5.5,
            pe_ratio=22.0,
            profit_margin=0.20,
            debt_to_equity=80.0,
            week_52_low=100.0,
            week_52_high=200.0,
        )

    monkeypatch.setattr(metrics_agent_mod, "fetch_metrics", fake_fetch)

    result = await metrics_agent_mod.metrics_agent({"ticker": "AAPL"})
    m: MetricsFindings = result["metrics"]
    assert m.status == "ok"
    assert m.revenue == 1.0e11
    assert m.eps == 5.5
    assert m.pe_ratio == 22.0
    assert m.profit_margin == 0.20
    assert m.debt_to_equity == 80.0
    assert m.week_52_low == 100.0
    assert m.week_52_high == 200.0


async def test_metrics_agent_unknown_ticker(monkeypatch):
    def boom(_ticker):
        raise MetricsClientError("No metrics available for ZZZZ")

    monkeypatch.setattr(metrics_agent_mod, "fetch_metrics", boom)

    result = await metrics_agent_mod.metrics_agent({"ticker": "ZZZZ"})
    m: MetricsFindings = result["metrics"]
    assert m.status == "error"
    assert m.failure and m.failure.stage == "financial review"


async def test_metrics_agent_unexpected_failure(monkeypatch):
    def boom(_ticker):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(metrics_agent_mod, "fetch_metrics", boom)

    result = await metrics_agent_mod.metrics_agent({"ticker": "AAPL"})
    m: MetricsFindings = result["metrics"]
    assert m.status == "error"
    assert "kaboom" not in (m.error or "")
    assert m.failure
