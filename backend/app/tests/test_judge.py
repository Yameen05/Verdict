"""Unit tests for the judge node and the reflection loop."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents.nodes import judge as judge_mod
from app.schemas.research import (
    Argument,
    DebateCase,
    EvidenceItem,
    MetricsFindings,
    NewsFindings,
    ResearchReport,
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
    if hasattr(judge_mod._client, "cache_clear"):
        judge_mod._client.cache_clear()
    yield
    if hasattr(judge_mod._client, "cache_clear"):
        judge_mod._client.cache_clear()


def _state() -> dict:
    evidence = [
        EvidenceItem(id="sec:0", source="sec", label="risks?", content="Supply chain."),
        EvidenceItem(id="metrics:margin", source="metrics", label="Profit margin", content="25.0%"),
    ]
    return {
        "ticker": "AAPL",
        "reflection_count": 0,
        "sec": SECFindings(
            status="ok",
            findings=[SECFinding(question="risks?", answer="Supply chain.", source_chunks=3)],
        ),
        "news": NewsFindings(status="ok", sentiment_score=0.4, article_count=5),
        "metrics": MetricsFindings(status="ok", profit_margin=0.25),
        "evidence": evidence,
        "bull": DebateCase(
            stance="bull", thesis="Compounding machine.",
            arguments=[Argument(claim="Strong margins", evidence=["metrics:margin"])],
        ),
        "bear": DebateCase(
            stance="bear", thesis="Priced for perfection.",
            arguments=[Argument(claim="Supply chain risk", evidence=["sec:0"])],
        ),
    }


def _verdict_json(**overrides) -> str:
    data = {
        "recommendation": "Buy",
        "confidence": 72,
        "justification": "Margins beat the bear case.",
        "dissent": "Supply chain risk was real but priced in.",
        "falsifiers": ["Margin drops below 20%"],
        "scores": {"valuation": 6, "growth": 7, "profitability": 9,
                   "balance_sheet": 5, "sentiment": 7},
        "citations": [{"claim": "25% margins", "evidence": ["metrics:margin", "bogus:id"]}],
        "company_overview": "Apple makes devices.",
        "financial_health": "25% margin.",
        "key_risks": ["Supply chain"],
        "news_summary": "Positive.",
        "delta_summary": None,
    }
    data.update(overrides)
    return json.dumps(data)


async def test_judge_full_verdict(monkeypatch):
    monkeypatch.setattr(judge_mod, "_client", lambda: _fake_openai_returning(_verdict_json()))
    out = await judge_mod.judge(_state())
    report: ResearchReport = out["report"]
    assert report.recommendation == "Buy"
    assert report.confidence == 72
    assert report.scores is not None and report.scores.profitability == 9
    assert report.falsifiers == ["Margin drops below 20%"]
    assert report.dissent and "Supply chain" in report.dissent
    # unknown evidence ids are stripped from citations
    assert report.citations[0].evidence == ["metrics:margin"]
    assert out["followup_question"] is None
    assert judge_mod.route_after_judge(out) == "__end__"


async def test_judge_short_circuits_when_no_agents_usable():
    state = {
        "ticker": "AAPL",
        "sec": SECFindings(status="skipped", error="ingest first"),
        "news": NewsFindings(status="skipped", error="no key"),
        "metrics": MetricsFindings(status="error", error="unknown ticker"),
    }
    out = await judge_mod.judge(state)
    assert out["report"].recommendation == "Pending"
    assert "No agent" in out["report"].justification


async def test_judge_handles_invalid_json(monkeypatch):
    monkeypatch.setattr(judge_mod, "_client", lambda: _fake_openai_returning("not json"))
    out = await judge_mod.judge(_state())
    assert out["report"].recommendation == "Pending"
    assert "parse" in out["report"].justification


async def test_judge_requests_followup_once(monkeypatch):
    monkeypatch.setattr(
        judge_mod,
        "_client",
        lambda: _fake_openai_returning(
            json.dumps({"recommendation": None, "needs_evidence": "What is the inventory trend?"})
        ),
    )
    out = await judge_mod.judge(_state())
    assert "report" not in out
    assert out["followup_question"] == "What is the inventory trend?"
    assert out["reflection_count"] == 1
    assert judge_mod.route_after_judge(out) == "followup"


async def test_judge_ignores_followup_after_reflection(monkeypatch):
    """Second pass must be final even if the model asks again."""
    monkeypatch.setattr(
        judge_mod,
        "_client",
        lambda: _fake_openai_returning(
            _verdict_json(needs_evidence="More please")
        ),
    )
    state = _state()
    state["reflection_count"] = 1
    out = await judge_mod.judge(state)
    assert out["report"].recommendation == "Buy"
    assert out["followup_question"] is None


async def test_followup_appends_evidence(monkeypatch):
    from app.services.vectorstore import QueryMatch

    async def fake_embed(_q):
        return [0.0] * 4

    async def fake_query(_ticker, _vec, top_k=3):
        return [QueryMatch(score=0.9, text="Inventory rose 12% YoY.", metadata={})]

    import app.services.embeddings as emb_mod
    import app.services.vectorstore as vs_mod

    monkeypatch.setattr(emb_mod, "embed_query", fake_embed)
    monkeypatch.setattr(vs_mod, "query", fake_query)

    state = _state()
    state["followup_question"] = "What is the inventory trend?"
    out = await judge_mod.followup(state)
    assert out["followup_question"] is None
    added = [e for e in out["evidence"] if e.id.startswith("sec:f")]
    assert added and "Inventory rose" in added[0].content


async def test_followup_survives_retrieval_failure(monkeypatch):
    async def boom(_q):
        raise RuntimeError("no embeddings key")

    import app.services.embeddings as emb_mod

    monkeypatch.setattr(emb_mod, "embed_query", boom)

    state = _state()
    state["followup_question"] = "Anything?"
    out = await judge_mod.followup(state)
    assert out["followup_question"] is None
    assert any(e.id == "sec:f0" for e in out["evidence"])
