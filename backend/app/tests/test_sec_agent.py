"""Unit tests for the SEC RAG agent node.

vectorstore.query and OpenAI client are monkey-patched so no network is hit.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.nodes import sec_agent as sec_agent_mod
from app.schemas.research import SECFindings
from app.services.sec_client import Filing
from app.services.vectorstore import QueryMatch


class _FakeChoice:
    def __init__(self, content: str):
        self.message = SimpleNamespace(content=content)


class _FakeResp:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeChatCompletions:
    async def create(self, **kwargs):
        return _FakeResp("Summarized answer.")


class _FakeChat:
    completions = _FakeChatCompletions()


class _FakeOpenAIClient:
    chat = _FakeChat()


@pytest.fixture
def patched_openai(monkeypatch):
    sec_agent_mod._client.cache_clear()
    monkeypatch.setattr(sec_agent_mod, "_client", lambda: _FakeOpenAIClient())
    yield


@pytest.fixture
def patched_embeddings(monkeypatch):
    async def fake_embed_query(_text: str) -> list[float]:
        return [0.0] * 1536

    monkeypatch.setattr(sec_agent_mod, "embed_query", fake_embed_query)
    yield


def _make_matches(n: int, accession: str = "0000320193-24-000123") -> list[QueryMatch]:
    return [
        QueryMatch(
            score=0.9 - i * 0.1,
            text=f"chunk {i}",
            metadata={"accession": accession, "chunk_index": i, "ticker": "AAPL"},
        )
        for i in range(n)
    ]


async def test_sec_agent_returns_findings_when_chunks_exist(
    patched_openai, patched_embeddings, monkeypatch
):
    async def fake_query(_ticker, _vector, top_k=5):
        return _make_matches(3)

    monkeypatch.setattr(sec_agent_mod.vectorstore, "query", fake_query)

    result = await sec_agent_mod.sec_agent({"ticker": "AAPL"})

    assert "sec" in result
    sec: SECFindings = result["sec"]
    assert sec.status == "ok"
    assert len(sec.findings) == len(sec_agent_mod.CANONICAL_QUESTIONS)
    for f in sec.findings:
        assert f.answer == "Summarized answer."
        assert f.source_chunks == 3
    assert sec.accession == "0000320193-24-000123"


def _fake_filing() -> Filing:
    return Filing(
        ticker="AAPL",
        cik="0000320193",
        form="10-K",
        accession="0000320193-26-000001",
        filing_date="2026-01-01",
        primary_document="aapl-10k.htm",
        raw_text=(
            "Risk factors include supply chain disruption and competition.\n\n"
            "Business segments include products and services revenue.\n\n"
            "Management discusses liquidity and cash position.\n\n"
            "Competitive threats include industry headwinds."
        ),
    )


async def test_sec_agent_uses_direct_filing_when_index_empty(
    patched_openai, patched_embeddings, monkeypatch
):
    async def fake_query(_ticker, _vector, top_k=5):
        return []

    async def fake_fetch_latest_10k(_ticker):
        return _fake_filing()

    monkeypatch.setattr(sec_agent_mod.vectorstore, "query", fake_query)
    monkeypatch.setattr(sec_agent_mod.sec_client, "fetch_latest_10k", fake_fetch_latest_10k)

    result = await sec_agent_mod.sec_agent({"ticker": "AAPL"})

    sec: SECFindings = result["sec"]
    assert sec.status == "ok"
    assert sec.accession == "0000320193-26-000001"
    assert len(sec.findings) == len(sec_agent_mod.CANONICAL_QUESTIONS)
    assert all(f.answer == "Summarized answer." for f in sec.findings)
    assert all(f.source_chunks > 0 for f in sec.findings)


async def test_sec_agent_skips_cleanly_when_index_and_direct_filing_fail(
    patched_openai, patched_embeddings, monkeypatch
):
    async def fake_query(_ticker, _vector, top_k=5):
        return []

    async def boom(_ticker):
        raise RuntimeError("SEC unavailable")

    monkeypatch.setattr(sec_agent_mod.vectorstore, "query", fake_query)
    monkeypatch.setattr(sec_agent_mod.sec_client, "fetch_latest_10k", boom)

    result = await sec_agent_mod.sec_agent({"ticker": "AAPL"})

    sec: SECFindings = result["sec"]
    assert sec.status == "skipped"
    assert sec.error and "direct filing read" in sec.error
    assert "POST" not in sec.error
    assert "Pinecone" not in sec.error


async def test_sec_agent_error_on_query_failure(
    patched_openai, patched_embeddings, monkeypatch
):
    async def boom(_ticker, _vector, top_k=5):
        raise RuntimeError("pinecone down")

    monkeypatch.setattr(sec_agent_mod.vectorstore, "query", boom)

    result = await sec_agent_mod.sec_agent({"ticker": "AAPL"})

    sec: SECFindings = result["sec"]
    assert sec.status == "error"
    assert sec.error and "pinecone down" in sec.error
