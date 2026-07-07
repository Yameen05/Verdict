"""Unit tests for the evidence ledger and the bull/bear advocates."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents.nodes import debate as debate_mod
from app.schemas.research import (
    Headline,
    InsiderFindings,
    InsiderTransaction,
    MetricsFindings,
    NewsFindings,
    SECFinding,
    SECFindings,
)


def _fake_openai_returning(content: str):
    class _C:
        async def create(self, **_kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    class _Chat:
        completions = _C()

    return SimpleNamespace(chat=_Chat())


@pytest.fixture(autouse=True)
def reset_client():
    if hasattr(debate_mod._client, "cache_clear"):
        debate_mod._client.cache_clear()
    yield
    if hasattr(debate_mod._client, "cache_clear"):
        debate_mod._client.cache_clear()


def _full_state() -> dict:
    return {
        "ticker": "AAPL",
        "sec": SECFindings(
            status="ok",
            findings=[SECFinding(question="risks?", answer="Supply chain.", source_chunks=3)],
            accession="ACC-1",
        ),
        "news": NewsFindings(
            status="ok",
            sentiment_score=0.4,
            summary="Positive coverage",
            article_count=10,
            top_headlines=[
                Headline(title="Apple beats estimates", source="Reuters", url="u", score=0.8)
            ],
        ),
        "metrics": MetricsFindings(
            status="ok",
            revenue=3.9e11,
            eps=6.16,
            pe_ratio=30.5,
            profit_margin=0.25,
            debt_to_equity=145.0,
            week_52_low=164.0,
            week_52_high=237.0,
            current_price=210.0,
        ),
        "insider": InsiderFindings(
            status="ok",
            transactions=[
                InsiderTransaction(
                    insider="Jane CEO", role="CEO", date="2026-06-01",
                    kind="buy", shares=1000, value_usd=210000.0,
                )
            ],
            buy_count=1,
            sell_count=0,
            summary="1 open-market buy.",
        ),
    }


def test_build_evidence_full_state():
    out = debate_mod.build_evidence(_full_state())
    ids = [e.id for e in out["evidence"]]
    assert "sec:0" in ids
    assert "news:sentiment" in ids
    assert "news:h0" in ids
    assert "metrics:pe" in ids
    assert "metrics:range" in ids
    assert "insider:net" in ids
    assert "insider:t0" in ids
    # ids must be unique — arguments cite them
    assert len(ids) == len(set(ids))


def test_build_evidence_skips_unusable_agents():
    state = {
        "ticker": "AAPL",
        "sec": SECFindings(status="skipped", error="not ingested"),
        "news": NewsFindings(status="error", error="boom"),
        "metrics": MetricsFindings(status="error", error="boom"),
    }
    out = debate_mod.build_evidence(state)
    assert out["evidence"] == []


async def test_advocate_filters_unknown_evidence_ids(monkeypatch):
    payload = json.dumps(
        {
            "thesis": "Apple compounds.",
            "arguments": [
                {"claim": "Margins are strong", "evidence": ["metrics:margin", "made:up"]},
                {"claim": "", "evidence": ["metrics:pe"]},  # dropped: empty claim
            ],
        }
    )
    monkeypatch.setattr(debate_mod, "_client", lambda: _fake_openai_returning(payload))

    state = _full_state()
    state["evidence"] = debate_mod.build_evidence(state)["evidence"]
    out = await debate_mod.bull_agent(state)
    case = out["bull"]
    assert case.status == "ok"
    assert case.thesis == "Apple compounds."
    assert len(case.arguments) == 1
    assert case.arguments[0].evidence == ["metrics:margin"]


async def test_advocate_skips_without_evidence():
    out = await debate_mod.bear_agent({"ticker": "AAPL", "evidence": []})
    assert out["bear"].status == "skipped"


async def test_advocate_handles_unparseable_output(monkeypatch):
    monkeypatch.setattr(debate_mod, "_client", lambda: _fake_openai_returning("nope"))
    state = _full_state()
    state["evidence"] = debate_mod.build_evidence(state)["evidence"]
    out = await debate_mod.bear_agent(state)
    assert out["bear"].status == "error"
