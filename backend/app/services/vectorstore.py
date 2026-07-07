"""Vector store facade — local SQLite by default, Pinecone when configured.

A 10-K is a few hundred chunks, so exact cosine over a local SQLite table is
plenty (and removes an API key + network hop from the demo path). Setting
PINECONE_API_KEY switches every call to the serverless Pinecone backend with
no other changes — the two backends share this module's interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.services.chunker import Chunk


@dataclass(slots=True)
class QueryMatch:
    score: float
    text: str
    metadata: dict[str, Any]


def backend_name() -> str:
    return "pinecone" if get_settings().pinecone_api_key else "local"


def _backend():
    if get_settings().pinecone_api_key:
        from app.services import vectorstore_pinecone as backend
    else:
        from app.services import vectorstore_local as backend
    return backend


async def upsert_chunks(
    ticker: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> int:
    return await _backend().upsert_chunks(ticker, chunks, vectors)


async def query(
    ticker: str,
    vector: list[float],
    top_k: int = 5,
) -> list[QueryMatch]:
    return await _backend().query(ticker, vector, top_k=top_k)
