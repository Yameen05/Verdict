"""Centralized LLM client factory.

Every chat-completion call site (the /research/ask chatbot, the synthesizer,
and the news & SEC agents) builds its client here, so the AI provider is
configured in ONE place. Point LLM_BASE_URL at any OpenAI-compatible endpoint
(e.g. Google Gemini's compatibility layer) and every call site follows along —
no code change needed to swap providers.
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

import httpx
from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from app.config import get_settings
from app.observability.cost import current_tracker
from app.services.research_events import emit_progress

GEMINI_FLASH_MODEL = "gemini-3.8-flash"
_pacing_lock = asyncio.Lock()
_last_chat_started: float | None = None


async def _pace_chat_request(request: httpx.Request) -> None:
    """One shared queue across chat clients; cancellation does not reserve a slot."""
    global _last_chat_started
    interval = get_settings().llm_min_interval_seconds
    if interval <= 0 or not request.url.path.rstrip("/").endswith("/chat/completions"):
        return
    wait_id = uuid4().hex
    waiting = _pacing_lock.locked() or (
        _last_chat_started is not None and time.monotonic() - _last_chat_started < interval
    )
    if waiting:
        emit_progress({"kind": "provider_wait", "id": wait_id, "reason": "queue", "phase": "started"})
    try:
        async with _pacing_lock:
            if _last_chat_started is not None:
                delay = interval - (time.monotonic() - _last_chat_started)
                if delay > 0:
                    await asyncio.sleep(delay)
            _last_chat_started = time.monotonic()
            tracker = current_tracker()
            if tracker is not None:
                tracker.chat_attempts += 1
    finally:
        if waiting:
            emit_progress({"kind": "provider_wait", "id": wait_id, "reason": "queue", "phase": "done"})


class CapacityRetryClient(DefaultAsyncHttpxClient):
    """Retry a temporary capacity failure once, through the same paced queue.

    Quota failures are surfaced immediately: retries cannot restore daily quota.
    The original model, endpoint and request body are preserved.
    """

    async def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        response = await super().send(request, **kwargs)
        if response.status_code != 503:
            return response
        await response.aclose()
        wait_id = uuid4().hex
        emit_progress({"kind": "provider_wait", "id": wait_id, "reason": "capacity", "phase": "started"})
        try:
            await asyncio.sleep(30)
        finally:
            emit_progress({"kind": "provider_wait", "id": wait_id, "reason": "capacity", "phase": "done"})
        return await super().send(request, **kwargs)


def chat_generation_options(temperature: float, max_tokens: int | None = None) -> dict:
    """Give Gemini 3 thinking room while preserving existing provider settings."""
    if get_settings().llm_model == GEMINI_FLASH_MODEL:
        options = {"temperature": 1.0, "max_tokens": max(32768, max_tokens or 0)}
        if max_tokens is not None:
            # Concise SEC summaries and chat replies need less deliberation.
            options["reasoning_effort"] = "low"
            options["max_tokens"] = max(8192, max_tokens)
        return options
    options = {"temperature": temperature}
    if max_tokens is not None:
        options["max_tokens"] = max_tokens
    return options


# Values that look configured but aren't — treated as "no key set".
_PLACEHOLDERS = {"placeholder", "changeme", "your-key-here", "none", "null", "todo"}


def llm_key_configured(key: str) -> bool:
    """True if `key` looks like a real provider key (not blank/placeholder).

    Provider-agnostic on purpose: OpenAI keys start with ``sk-`` while Gemini
    keys start with ``AIza`` — so we check for a real, non-placeholder value
    rather than a specific prefix.
    """
    k = (key or "").strip()
    return bool(k) and k.lower() not in _PLACEHOLDERS and len(k) >= 20


def make_llm_client(timeout: float | None = None) -> AsyncOpenAI:
    """Build an AsyncOpenAI client pointed at the configured provider.

    Uses ``resolved_llm_key`` (LLM_API_KEY, falling back to OPENAI_API_KEY) and,
    when LLM_BASE_URL is set, routes to that OpenAI-compatible endpoint.
    """
    s = get_settings()
    effective_timeout = (
        timeout if timeout is not None else (120.0 if s.llm_model == GEMINI_FLASH_MODEL else 60.0)
    )
    kwargs: dict = {"api_key": s.resolved_llm_key, "timeout": effective_timeout}
    if s.llm_min_interval_seconds > 0:
        kwargs["http_client"] = CapacityRetryClient(event_hooks={"request": [_pace_chat_request]})
        # Only CapacityRetryClient retries, once for 503; never burst on quota errors.
        kwargs["max_retries"] = 0
    base = s.llm_base_url.strip()
    if base:
        kwargs["base_url"] = base
    return AsyncOpenAI(**kwargs)
