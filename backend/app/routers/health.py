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


async def _check_pinecone() -> tuple[bool, str]:
    settings = get_settings()
    if not settings.pinecone_api_key:
        return False, "PINECONE_API_KEY not set"
    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=settings.pinecone_api_key)
        names = pc.list_indexes().names()
        return True, f"reachable ({len(names)} indexes)"
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
    llm_ok, news_ok, pc_ok = await asyncio.gather(
        _check_llm(), _check_newsapi(), _check_pinecone()
    )
    checks = {
        "llm": {"ok": llm_ok[0], "detail": llm_ok[1]},
        "newsapi": {"ok": news_ok[0], "detail": news_ok[1]},
        "pinecone": {"ok": pc_ok[0], "detail": pc_ok[1]},
    }
    all_ok = all(c["ok"] for c in checks.values())
    if not all_ok:
        response.status_code = 503
    return {"status": "ready" if all_ok else "degraded", "checks": checks}
