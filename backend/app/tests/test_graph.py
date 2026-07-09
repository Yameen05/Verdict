"""End-to-end smoke test for the assembled LangGraph trial.

All external dependencies (vectorstore, OpenAI, NewsAPI, yfinance, EDGAR) are
stubbed; this verifies fan-out → evidence ledger → bull/bear debate → judge
wiring, and that the final ResearchResponse carries the verdict extensions.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agents import graph as graph_mod
from app.agents.nodes import debate as debate_mod
from app.agents.nodes import insider_agent as insider_agent_mod
from app.agents.nodes import judge as judge_mod
from app.agents.nodes import metrics_agent as metrics_agent_mod
from app.agents.nodes import news_agent as news_agent_mod
from app.agents.nodes import sec_agent as sec_agent_mod
from app.agents.nodes import signals_agent as signals_agent_mod
from app.config import get_settings
from app.services.insider_client import Form4Transaction
from app.services.metrics_client import Metrics
from app.services.sentiment import ScoredArticle


def _fake_openai_returning(content: str):
    class _C:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    class _Chat:
        completions = _C()

    return SimpleNamespace(chat=_Chat())


def _fake_advocate_client():
    """One client whose reply is a valid advocate case for either stance."""
    payload = json.dumps(
        {
            "thesis": "The evidence supports this side.",
            "arguments": [
                {"claim": "Margins are excellent", "evidence": ["metrics:margin"]},
                {"claim": "Filing flags supply chain", "evidence": ["sec:0"]},
            ],
        }
    )
    return _fake_openai_returning(payload)


_VERDICT = {
    "recommendation": "Buy",
    "confidence": 78,
    "justification": "Bull case carried: 25.3% margins and insider buying beat the risk story.",
    "dissent": "Supply chain exposure is real but already reflected in the range.",
    "falsifiers": ["Margin below 20% next quarter", "Insider selling cluster"],
    "scores": {"valuation": 6, "growth": 7, "profitability": 9, "balance_sheet": 6, "sentiment": 7},
    "citations": [{"claim": "25.3% profit margin", "evidence": ["metrics:margin"]}],
    "company_overview": "Apple makes consumer electronics.",
    "financial_health": "TTM revenue $394B with 25.3% profit margin.",
    "key_risks": ["Supply chain"],
    "news_summary": "Recent earnings beat estimates.",
    "delta_summary": None,
}


@pytest.fixture
def stub_externals(monkeypatch):
    for mod in (sec_agent_mod, debate_mod, judge_mod):
        if hasattr(mod._client, "cache_clear"):
            mod._client.cache_clear()
    graph_mod.get_graph.cache_clear()
    get_settings.cache_clear()
    metrics_agent_mod._reset_cache()
    news_agent_mod._reset_news_cache()
    insider_agent_mod._reset_cache()
    signals_agent_mod._reset_cache()

    # --- SEC ---
    async def fake_embed_query(_t):
        return [0.0] * 1536

    async def fake_query(_ticker, _vec, top_k=5):
        from app.services.vectorstore import QueryMatch

        return [
            QueryMatch(
                score=0.8,
                text="Apple faces supply-chain risk.",
                metadata={"accession": "ACC-1", "chunk_index": 0, "ticker": "AAPL"},
            )
        ]

    monkeypatch.setattr(sec_agent_mod, "embed_query", fake_embed_query)
    monkeypatch.setattr(sec_agent_mod.vectorstore, "query", fake_query)
    monkeypatch.setattr(
        sec_agent_mod, "_client", lambda: _fake_openai_returning("Short answer.")
    )

    # --- News ---
    monkeypatch.setenv("NEWS_API_KEY", "test-key")

    async def fake_lookup_company_name(_ticker, client=None):
        return "Apple Inc."

    async def fake_fetch_articles(_ticker, _company):
        from app.services.news_client import Article

        return [
            Article(
                title="Apple reports strong quarterly earnings",
                description="Revenue beats estimates.",
                source="Reuters",
                url="u",
                published_at="2026-05-22T12:00:00Z",
            )
        ]

    async def fake_score(_company, articles):
        return 0.5, [ScoredArticle(article=a, score=0.5) for a in articles], "Positive."

    monkeypatch.setattr(news_agent_mod.sec_client, "lookup_company_name", fake_lookup_company_name)
    monkeypatch.setattr(news_agent_mod, "fetch_market_articles", fake_fetch_articles)
    monkeypatch.setattr(news_agent_mod, "score_and_summarize", fake_score)

    # --- Metrics ---
    def fake_fetch_metrics(_ticker):
        return Metrics(
            revenue=394e9,
            eps=6.16,
            pe_ratio=30.5,
            profit_margin=0.253,
            debt_to_equity=145.0,
            week_52_low=164.08,
            week_52_high=237.49,
            current_price=210.0,
        )

    monkeypatch.setattr(metrics_agent_mod, "fetch_metrics", fake_fetch_metrics)

    # --- Insider ---
    async def fake_form4(_ticker, max_filings=8):
        return [
            Form4Transaction(
                insider="DOE JANE", role="CEO", date="2026-06-15",
                code="P", kind="buy", shares=1000, value_usd=210500.0,
            )
        ]

    monkeypatch.setattr(insider_agent_mod, "fetch_recent_form4", fake_form4)

    # --- Debate + Judge ---
    monkeypatch.setattr(debate_mod, "_client", _fake_advocate_client)
    monkeypatch.setattr(
        judge_mod, "_client", lambda: _fake_openai_returning(json.dumps(_VERDICT))
    )

    yield
    get_settings.cache_clear()


async def test_graph_end_to_end_full_trial(stub_externals):
    result = await graph_mod.run_research("AAPL")

    assert result.ticker == "AAPL"
    assert result.sec.status == "ok"
    assert result.news.status == "ok"
    assert result.metrics.status == "ok"
    assert result.insider.status == "ok"
    assert result.signals.status == "skipped"
    assert result.metrics.profit_margin == pytest.approx(0.253)
    assert result.metrics.current_price == pytest.approx(210.0)

    # Evidence ledger built from all configured agents.
    ids = {e.id for e in result.evidence}
    assert {"sec:0", "news:sentiment", "metrics:margin", "insider:net"} <= ids

    # Both advocates argued and cited real evidence.
    assert result.bull is not None and result.bull.status == "ok"
    assert result.bear is not None and result.bear.status == "ok"
    assert result.bull.arguments[0].evidence == ["metrics:margin"]

    # Judge issued the full verdict.
    assert result.report.recommendation == "Buy"
    assert result.report.confidence == 78
    assert result.report.scores is not None
    assert result.report.falsifiers
    assert result.report.dissent
    assert result.report.citations[0].evidence == ["metrics:margin"]
    assert "Supply chain" in result.report.key_risks


async def test_graph_prior_run_reaches_judge(stub_externals, monkeypatch):
    """prior_run flows into the judge prompt (delta_summary comes back)."""
    verdict = dict(_VERDICT)
    verdict["delta_summary"] = "Upgraded from Hold: margins improved."
    monkeypatch.setattr(
        judge_mod, "_client", lambda: _fake_openai_returning(json.dumps(verdict))
    )
    prior = {
        "recommendation": "Hold",
        "justification": "Mixed signals last time.",
        "created_at": "2026-06-01T00:00:00+00:00",
        "price_at_run": 200.0,
    }
    result = await graph_mod.run_research("AAPL", prior)
    assert result.report.delta_summary == "Upgraded from Hold: margins improved."


async def test_graph_astream_emits_updates_and_custom_events(stub_externals):
    """The SSE layer multiplexes stream modes; verify the contract it expects."""
    graph = graph_mod.get_graph()
    modes_seen: set[str] = set()
    nodes_completed: list[str] = []
    custom_kinds: list[str] = []

    async for mode, chunk in graph.astream(
        graph_mod.initial_state("AAPL"), stream_mode=["updates", "custom"]
    ):
        modes_seen.add(mode)
        if mode == "updates":
            nodes_completed.extend(chunk.keys())
        else:
            custom_kinds.append(chunk.get("kind"))

    assert modes_seen == {"updates", "custom"}
    for node in ("sec_agent", "news_agent", "metrics_agent", "insider_agent", "signals_agent",
                 "build_evidence", "bull_agent", "bear_agent", "judge"):
        assert node in nodes_completed, node
    # advocates + judge emit progress over the custom stream
    assert "debate_case" in custom_kinds
    assert "judge_phase" in custom_kinds
