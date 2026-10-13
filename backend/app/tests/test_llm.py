"""Tests for provider-agnostic LLM configuration helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.config import get_settings
from app.services import llm as llm_mod
from app.services.llm import chat_generation_options, llm_key_configured, make_llm_client


def test_llm_key_configured_rejects_placeholders():
    assert llm_key_configured("") is False
    assert llm_key_configured("placeholder") is False
    assert llm_key_configured("your-key-here") is False
    assert llm_key_configured("short") is False


def test_llm_key_configured_accepts_provider_shaped_keys():
    assert llm_key_configured("sk-" + "x" * 40) is True
    assert llm_key_configured("AIza" + "x" * 36) is True


def test_resolved_llm_key_uses_openai_when_no_custom_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "o" * 40)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    get_settings.cache_clear()

    assert get_settings().resolved_llm_key == "sk-" + "o" * 40


def test_resolved_llm_key_prefers_llm_api_key(monkeypatch):
    provider_key = "AIza" + "g" * 36
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "o" * 40)
    monkeypatch.setenv("LLM_API_KEY", provider_key)
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/openai/v1")
    get_settings.cache_clear()

    assert get_settings().resolved_llm_key == provider_key


def test_custom_base_url_does_not_reuse_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "o" * 40)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/openai/v1")
    get_settings.cache_clear()

    assert get_settings().resolved_llm_key == ""


def test_flash38_leaves_room_for_thinking_and_uses_supported_effort(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("LLM_API_KEY", "test-" + "x" * 32)
    monkeypatch.setenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    get_settings.cache_clear()
    for cap in [200, 700]:
        assert chat_generation_options(0.1, cap) == {
            "temperature": 1.0,
            "max_tokens": 8192,
            "reasoning_effort": "low",
        }
    assert chat_generation_options(0.2) == {"temperature": 1.0, "max_tokens": 32768}
    client = make_llm_client()
    assert client.timeout == 120.0
    assert str(client.base_url) == get_settings().llm_base_url
    assert make_llm_client(timeout=5).timeout == 5


def test_other_models_keep_existing_generation_options(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini-2.5-flash")
    get_settings.cache_clear()
    assert chat_generation_options(0.1, 200) == {"temperature": 0.1, "max_tokens": 200}
    assert chat_generation_options(0.2) == {"temperature": 0.2}


@pytest.mark.asyncio
async def test_separate_clients_share_free_quota_pacing(monkeypatch):
    monkeypatch.setenv("LLM_MIN_INTERVAL_SECONDS", "13")
    monkeypatch.setenv("LLM_API_KEY", "test-" + "x" * 32)
    get_settings.cache_clear()
    clock = [0.0]
    starts = []

    async def sleep(delay):
        clock[0] += delay
        await asyncio.sleep(0)

    async def handle(request):
        starts.append(clock[0])
        return httpx.Response(
            200,
            json={
                "id": "smoke",
                "object": "chat.completion",
                "created": 0,
                "model": "gemini-3.8-flash",
                "choices": [],
            },
        )

    monkeypatch.setattr(llm_mod, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(llm_mod, "asyncio", SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(llm_mod, "_pacing_lock", asyncio.Lock())
    monkeypatch.setattr(llm_mod, "_last_chat_started", None)
    monkeypatch.setattr(
        llm_mod,
        "CapacityRetryClient",
        lambda **kw: httpx.AsyncClient(
            transport=httpx.MockTransport(handle),
            **kw,
        ),
    )
    async with make_llm_client() as first, make_llm_client() as second:
        assert first.max_retries == 0
        await asyncio.gather(
            *[
                client.chat.completions.create(model="gemini-3.8-flash", messages=[])
                for client in [first, second, first, second]
            ]
        )
    assert starts == [0, 13, 26, 39]


@pytest.mark.parametrize("statuses,expected", [([503, 200], 2), ([503, 503], 2), ([429], 1)])
async def test_capacity_retry_is_bounded_and_never_retries_quota(monkeypatch, statuses, expected):
    delays = []
    requests = []

    async def sleep(delay):
        delays.append(delay)

    async def handle(request):
        requests.append(request.content)
        return httpx.Response(statuses[len(requests) - 1], json={})

    monkeypatch.setattr(llm_mod, "asyncio", SimpleNamespace(sleep=sleep))
    async with llm_mod.CapacityRetryClient(transport=httpx.MockTransport(handle)) as client:
        result = await client.post(
            "https://example.test/chat/completions", json={"model": "gemini-3.8-flash"}
        )
    assert len(requests) == expected
    assert result.status_code == statuses[-1]
    assert all(body == requests[0] for body in requests)
    assert delays == ([30] if expected == 2 else [])
