"""Tests for POST /research/ask (conversational follow-up).

Critical regression guard: `/research/ask` must reach the `ask` handler. It is
declared on the same router as the dynamic `POST /research/{ticker}` route, and
because Starlette matches in registration order, `/ask` must be registered
*before* `/{ticker}` — otherwise a chat request is silently treated as a
research run for ticker "ASK" and the chatbot breaks.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.limiter import limiter
from app.routers import ask as research_mod


@pytest.fixture(autouse=True)
def _reset_limiter():
    """The slowapi limiter uses process-global in-memory storage; clear it so
    request counts don't leak between tests."""
    limiter.reset()
    yield
    limiter.reset()


def _fake_ask_client(content: str):
    class _Completions:
        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                usage=SimpleNamespace(prompt_tokens=12, completion_tokens=34),
            )

    class _Chat:
        completions = _Completions()

    return SimpleNamespace(chat=_Chat())


def test_ask_route_is_not_shadowed_by_ticker_route(client, monkeypatch):
    """With a placeholder key, /research/ask returns the ask handler's own 503.

    Only the `ask` endpoint emits the LLM-key 503; `research(ticker="ask")`
    never does. So this status+detail proves the request reached `ask`.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    get_settings.cache_clear()

    resp = client.post(
        "/research/ask",
        json={
            "ticker": "AAPL",
            "question": "What are the principal risks?",
            "context": None,
            "history": [],
        },
    )

    assert resp.status_code == 503
    assert "LLM API key" in resp.json()["detail"]


def test_ask_returns_answer_with_valid_key(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 40)
    get_settings.cache_clear()
    monkeypatch.setattr(
        research_mod, "_ask_client", lambda: _fake_ask_client("Apple looks resilient.")
    )

    resp = client.post(
        "/research/ask",
        json={
            "ticker": "AAPL",
            "question": "Is the balance sheet healthy?",
            "context": None,
            "history": [{"role": "user", "content": "hi"}],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Apple looks resilient."
    assert body["cost_usd"] >= 0
    assert "request_id" in body


def test_ask_rejects_blank_question(client, monkeypatch):
    """Validation runs at the ask endpoint, not the research route."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 40)
    get_settings.cache_clear()

    resp = client.post(
        "/research/ask",
        json={"ticker": "AAPL", "question": "", "context": None, "history": []},
    )

    assert resp.status_code == 422


def test_ask_is_rate_limited(client, monkeypatch):
    """The @limiter.limit on /ask must actually fire. With a 2/minute cap, the
    third request in the window is rejected with 429 (not a 4th LLM call)."""
    monkeypatch.setenv("RATE_LIMIT_RESEARCH", "2/minute")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "x" * 40)
    get_settings.cache_clear()
    monkeypatch.setattr(research_mod, "_ask_client", lambda: _fake_ask_client("ok"))

    payload = {"ticker": "AAPL", "question": "Quick one?", "context": None, "history": []}
    statuses = [client.post("/research/ask", json=payload).status_code for _ in range(3)]

    assert statuses[:2] == [200, 200], f"first two should pass, got {statuses}"
    assert statuses[2] == 429, f"third should be rate-limited, got {statuses}"
