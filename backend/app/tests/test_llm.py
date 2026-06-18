"""Tests for provider-agnostic LLM configuration helpers."""

from __future__ import annotations

from app.config import get_settings
from app.services.llm import llm_key_configured


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
