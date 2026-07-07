"""Round-trip tests for the local SQLite vector backend."""

from __future__ import annotations

import pytest

from app.services import vectorstore, vectorstore_local
from app.services.chunker import Chunk


def _chunk(i: int, accession: str = "ACC-1", text: str | None = None) -> Chunk:
    return Chunk(
        text=text or f"chunk text {i}",
        metadata={
            "accession": accession,
            "chunk_index": i,
            "ticker": "AAPL",
            "form": "10-K",
            "filing_date": "2026-01-01",
        },
    )


async def test_upsert_and_query_roundtrip():
    chunks = [_chunk(0, text="supply chain risks"), _chunk(1, text="revenue growth")]
    vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    n = await vectorstore_local.upsert_chunks("AAPL", chunks, vectors)
    assert n == 2

    matches = await vectorstore_local.query("AAPL", [0.9, 0.1, 0.0], top_k=1)
    assert len(matches) == 1
    assert matches[0].text == "supply chain risks"
    assert matches[0].metadata["accession"] == "ACC-1"
    assert matches[0].score == pytest.approx(0.9 / (0.9**2 + 0.1**2) ** 0.5, abs=1e-4)


async def test_reingest_replaces_accession():
    await vectorstore_local.upsert_chunks("AAPL", [_chunk(0), _chunk(1)], [[1, 0], [0, 1]])
    # Re-ingest same accession with fewer chunks — old ones must not linger.
    await vectorstore_local.upsert_chunks("AAPL", [_chunk(0, text="fresh")], [[1, 0]])
    assert vectorstore_local.count_chunks_sync("AAPL") == 1
    matches = await vectorstore_local.query("AAPL", [1, 0], top_k=5)
    assert [m.text for m in matches] == ["fresh"]


async def test_query_unknown_ticker_returns_empty():
    assert await vectorstore_local.query("ZZZZ", [1.0, 0.0]) == []


async def test_facade_routes_to_local_without_pinecone_key(monkeypatch):
    monkeypatch.setenv("PINECONE_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()
    assert vectorstore.backend_name() == "local"
    await vectorstore.upsert_chunks("MSFT", [_chunk(0)], [[1.0, 0.0]])
    matches = await vectorstore.query("MSFT", [1.0, 0.0])
    assert len(matches) == 1
