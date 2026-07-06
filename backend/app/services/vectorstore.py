"""Pinecone serverless vectorstore wrapper.

One index, namespace-per-ticker so per-ticker reingest is a single delete.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from pinecone import Pinecone, ServerlessSpec

from app.config import get_settings
from app.observability.logging import get_logger
from app.services.chunker import Chunk

log = get_logger(__name__)


@dataclass(slots=True)
class QueryMatch:
    score: float
    text: str
    metadata: dict[str, Any]


@lru_cache(maxsize=1)
def _pc() -> Pinecone:
    return Pinecone(api_key=get_settings().pinecone_api_key)


def _ensure_index() -> Any:
    settings = get_settings()
    pc = _pc()
    name = settings.pinecone_index_name
    existing = set(pc.list_indexes().names())
    if name not in existing:
        pc.create_index(
            name=name,
            dimension=settings.embedding_dim,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=settings.pinecone_cloud,
                region=settings.pinecone_region,
            ),
        )
    return pc.Index(name)


def _namespace_for(ticker: str) -> str:
    return ticker.upper()


async def upsert_chunks(
    ticker: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> int:
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors length mismatch")
    if not chunks:
        return 0

    namespace = _namespace_for(ticker)
    accession = chunks[0].metadata["accession"]

    def _sync():
        index = _ensure_index()
        # Best-effort: drop prior copies of the same accession so re-ingest is
        # clean even if chunk_count shrinks. Serverless indexes may reject
        # delete-by-filter; the upsert below still overwrites by id, so a
        # failure here just leaves trailing chunks from a previous run.
        try:
            index.delete(filter={"accession": accession}, namespace=namespace)
        except Exception as exc:  # noqa: BLE001 - delete is best-effort
            log.warning(
                "vectorstore_cleanup_failed",
                extra={
                    "ticker": ticker,
                    "accession": accession,
                    "error_type": type(exc).__name__,
                },
            )

        vectors_payload = [
            {
                "id": f"{accession}-{c.metadata['chunk_index']}",
                "values": vec,
                "metadata": {**c.metadata, "text": c.text},
            }
            for c, vec in zip(chunks, vectors, strict=True)
        ]
        # Batch to stay well under Pinecone's request size cap.
        for i in range(0, len(vectors_payload), 100):
            index.upsert(vectors=vectors_payload[i : i + 100], namespace=namespace)
        return len(vectors_payload)

    return await asyncio.to_thread(_sync)


async def query(
    ticker: str,
    vector: list[float],
    top_k: int = 5,
) -> list[QueryMatch]:
    namespace = _namespace_for(ticker)

    def _sync():
        index = _ensure_index()
        result = index.query(
            vector=vector,
            top_k=top_k,
            include_metadata=True,
            namespace=namespace,
        )
        out: list[QueryMatch] = []
        for m in result.get("matches", []):
            md = dict(m.get("metadata") or {})
            text = md.pop("text", "")
            out.append(QueryMatch(score=float(m.get("score", 0.0)), text=text, metadata=md))
        return out

    return await asyncio.to_thread(_sync)


def init_index_sync() -> str:
    """Idempotent index creation. Returns the index name."""
    _ensure_index()
    return get_settings().pinecone_index_name
