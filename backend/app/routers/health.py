"""Liveness + readiness probes.

  GET /health        → 200 always (process is up)
  GET /health/ready  → 200 only if all configured upstreams reachable;
                       503 otherwise, with a per-dependency breakdown.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Depends, Response

from app.config import get_settings
from app.observability.logging import get_logger
from app.security import AuthContext, require_authenticated

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _check_llm() -> tuple[bool, str]:
    settings = get_settings()
    if not settings.resolved_llm_key:
        return False, "No LLM API key set (LLM_API_KEY / OPENAI_API_KEY)"
    try:
        from app.services.llm import make_llm_client

        client = make_llm_client(timeout=5.0)
        await client.models.list()
        return True, "reachable"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


async def _check_vectorstore() -> tuple[bool, str]:
    settings = get_settings()
    if settings.pinecone_api_key:
        try:
            from pinecone import Pinecone

            pc = Pinecone(api_key=settings.pinecone_api_key)
            names = pc.list_indexes().names()
            return True, f"pinecone reachable ({len(names)} indexes)"
        except Exception as e:  # noqa: BLE001
            return False, type(e).__name__
    try:
        from app.services.vectorstore_local import count_chunks_sync

        count = await asyncio.to_thread(count_chunks_sync)
        return True, f"local ({count} chunks indexed)"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


async def _check_newsapi() -> tuple[bool, str]:
    settings = get_settings()
    if not settings.news_api_key:
        return True, "skipped (no key — optional)"
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                "https://newsapi.org/v2/everything",
                params={"q": "test", "pageSize": 1, "apiKey": settings.news_api_key},
            )
            if r.status_code == 200:
                return True, "reachable"
            return False, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


@router.get("/health/ready")
async def ready(
    response: Response,
    _auth: AuthContext = Depends(require_authenticated),
) -> dict:
    llm_ok, news_ok, vs_ok = await asyncio.gather(
        _check_llm(), _check_newsapi(), _check_vectorstore()
    )
    checks = {
        "llm": {"ok": llm_ok[0], "detail": llm_ok[1]},
        "newsapi": {"ok": news_ok[0], "detail": news_ok[1]},
        "vectorstore": {"ok": vs_ok[0], "detail": vs_ok[1]},
    }
    all_ok = all(c["ok"] for c in checks.values())
    if not all_ok:
        response.status_code = 503
    return {"status": "ready" if all_ok else "degraded", "checks": checks}


@router.get("/health/config")
async def config_status(
    _auth: AuthContext = Depends(require_authenticated),
) -> dict:
    """Authenticated runtime configuration summary with no secret values."""
    settings = get_settings()
    signal_keys = {
        "finnhub": bool(settings.finnhub_api_key.strip()),
        "alphavantage": bool(settings.alphavantage_api_key.strip()),
        "polygon": bool(settings.polygon_api_key.strip()),
        "tiingo": bool(settings.tiingo_api_key.strip()),
        "fred": bool(settings.fred_api_key.strip()),
        "stocktwits": settings.stocktwits_enabled,
        "reddit": settings.reddit_enabled,
    }
    provider = "openai"
    if settings.llm_base_url.strip():
        provider = settings.llm_base_url.strip().split("//")[-1].split("/")[0]
    vectorstore = "pinecone" if settings.pinecone_api_key.strip() else "local"
    return {
        "environment": settings.environment,
        "llm": {
            "provider": provider,
            "model": settings.llm_model,
            "configured": bool(settings.resolved_llm_key),
            "rate_limit": settings.rate_limit_research,
        },
        "embeddings": {
            "model": settings.embedding_model,
            "configured": bool(settings.resolved_embedding_key),
        },
        "sources": {
            "newsapi": bool(settings.news_api_key.strip()),
            "vectorstore": vectorstore,
            "signals": signal_keys,
            "signals_cache_seconds": settings.signals_cache_seconds,
        },
        "quotas": {
            "research_cache_minutes": settings.research_cache_minutes,
            "daily_runs_per_user": settings.daily_runs_per_user,
            "daily_runs_global": settings.daily_runs_global,
        },
    }
