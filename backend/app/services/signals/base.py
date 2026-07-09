"""Shared HTTP helper for signal providers."""

from __future__ import annotations

from typing import Any

import httpx

from app.observability.logging import get_logger

log = get_logger(__name__)


async def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> Any | None:
    """GET and parse JSON, returning None on any failure (best-effort)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:  # noqa: BLE001 - providers are best-effort context
        log.info("signal_provider_failed", extra={"url": url, "reason": str(e)[:120]})
        return None


def to_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None", "-"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
