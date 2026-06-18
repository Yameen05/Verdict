"""Centralized LLM client factory.

Every chat-completion call site (the /research/ask chatbot, the synthesizer,
and the news & SEC agents) builds its client here, so the AI provider is
configured in ONE place. Point LLM_BASE_URL at any OpenAI-compatible endpoint
(e.g. Google Gemini's compatibility layer) and every call site follows along —
no code change needed to swap providers.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from app.config import get_settings

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


def make_llm_client(timeout: float = 60.0) -> AsyncOpenAI:
    """Build an AsyncOpenAI client pointed at the configured provider.

    Uses ``resolved_llm_key`` (LLM_API_KEY, falling back to OPENAI_API_KEY) and,
    when LLM_BASE_URL is set, routes to that OpenAI-compatible endpoint.
    """
    s = get_settings()
    kwargs: dict = {"api_key": s.resolved_llm_key, "timeout": timeout}
    base = s.llm_base_url.strip()
    if base:
        kwargs["base_url"] = base
    return AsyncOpenAI(**kwargs)
