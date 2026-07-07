"""OpenAI embeddings wrapper with cost tracking.

Uses text-embedding-3-small (1536 dims) by default. Batches in groups of 100
inputs per API call to respect rate/size limits.
"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from app.config import get_settings
from app.observability.cost import record_embedding
from app.observability.logging import get_logger

log = get_logger(__name__)
_BATCH_SIZE = 100


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    # Follows EMBEDDING_BASE_URL when set (any OpenAI-compatible provider,
    # e.g. Gemini's compatibility layer); defaults to api.openai.com.
    s = get_settings()
    kwargs: dict = {"api_key": s.resolved_embedding_key, "timeout": 60.0}
    if s.embedding_base_url.strip():
        kwargs["base_url"] = s.embedding_base_url.strip()
    return AsyncOpenAI(**kwargs)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    settings = get_settings()
    client = _client()
    vectors: list[list[float]] = []

    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        resp = await client.embeddings.create(model=settings.embedding_model, input=batch)
        record_embedding(settings.embedding_model, resp)
        vectors.extend([item.embedding for item in resp.data])

    log.info(
        "embed_texts_completed",
        extra={"count": len(texts), "model": settings.embedding_model},
    )
    return vectors


async def embed_query(text: str) -> list[float]:
    result = await embed_texts([text])
    return result[0]
