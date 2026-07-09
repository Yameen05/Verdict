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
from app.services.metrics_client import HorizonStats


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


def _research_context(recommendation: str = "Sell") -> dict:
    return {
        "ticker": "NVDA",
        "sec": {"status": "skipped"},
        "news": {
            "status": "ok",
            "sentiment_score": 0.1,
            "summary": "Mixed recent news.",
        },
        "metrics": {
            "status": "ok",
            "current_price": 50,
            "horizon_days": 14,
            "recent_return_pct": -3,
            "typical_swing_pct": 8,
            "best_window_pct": 18,
            "worst_window_pct": -15,
        },
        "report": {
            "ticker": "NVDA",
            "recommendation": recommendation,
            "justification": "The downside case is stronger for this holding window.",
            "company_overview": "Nvidia sells chips used in AI systems.",
            "financial_health": "Profitable, but expectations are demanding.",
            "horizon_days": 14,
            "simple_summary": "The stock could move a lot over this short window.",
        },
    }


def _fake_horizon_stats(_ticker: str, days: int) -> HorizonStats:
    data = {
        7: HorizonStats(7, recent_return_pct=2, typical_swing_pct=3, best_window_pct=10, worst_window_pct=-8),
        30: HorizonStats(30, recent_return_pct=4, typical_swing_pct=12, best_window_pct=28, worst_window_pct=-20),
        90: HorizonStats(90, recent_return_pct=9, typical_swing_pct=22, best_window_pct=55, worst_window_pct=-35),
        365: HorizonStats(365, recent_return_pct=40, typical_swing_pct=45, best_window_pct=180, worst_window_pct=-55),
    }
    return data[days]


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


def test_investment_question_returns_simple_dollar_windows_without_llm(
    client, monkeypatch
):
    monkeypatch.setattr(research_mod, "_ask_client", lambda: pytest.fail("LLM was called"))
    monkeypatch.setattr(research_mod, "fetch_horizon_stats", _fake_horizon_stats)

    resp = client.post(
        "/research/ask",
        json={
            "ticker": "NVDA",
            "question": "If I invest 200 dollars right now, what should I get in 1 week, what about 2 weeks and on?",
            "context": _research_context("Sell"),
            "history": [],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    answer = body["answer"]
    assert body["cost_usd"] == 0
    assert "If you put $200 into NVDA right now" in answer
    assert "you would own about 4.0000 shares" in answer
    assert "Plain answer: the report says Sell for 2 weeks" in answer
    assert "1 week: usually about $194-$206" in answer
    assert "2 weeks: usually about $184-$216" in answer
    assert "1 month:" in answer
    assert "Nobody can know the exact future number" in answer


def test_past_investment_question_returns_current_return_and_hold_guidance(
    client, monkeypatch
):
    monkeypatch.setattr(research_mod, "_ask_client", lambda: pytest.fail("LLM was called"))
    monkeypatch.setattr(research_mod, "fetch_horizon_stats", _fake_horizon_stats)

    resp = client.post(
        "/research/ask",
        json={
            "ticker": "NVDA",
            "question": "I invested 100 last week, should I sell it right now or hold? How long do I hold for, and what would my return be if I hold later?",
            "context": _research_context("Sell"),
            "history": [],
        },
    )

    assert resp.status_code == 200
    answer = resp.json()["answer"]
    assert "it would be about $102 right now" in answer
    assert "$2 gain (+2.00%)" in answer
    assert "Plain answer: the report says Sell for 2 weeks" in answer
    assert "How long: this report does not support holding longer" in answer
    assert "If you keep holding from today's estimated value" in answer
    assert "1 week: usually about $98.94-$105.06" in answer


def test_sell_or_hold_question_without_amount_still_gets_plain_guidance(
    client, monkeypatch
):
    monkeypatch.setattr(research_mod, "_ask_client", lambda: pytest.fail("LLM was called"))
    monkeypatch.setattr(
        research_mod,
        "fetch_horizon_stats",
        lambda *_args, **_kwargs: pytest.fail("price history was called"),
    )

    resp = client.post(
        "/research/ask",
        json={
            "ticker": "NVDA",
            "question": "Should I sell it right now or hold?",
            "context": _research_context("Sell"),
            "history": [],
        },
    )

    assert resp.status_code == 200
    answer = resp.json()["answer"]
    assert "Plain answer: the report says Sell for 2 weeks" in answer
    assert "How long: this report does not support holding longer" in answer
    assert "I need the dollar amount and when you bought to calculate your return" in answer


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
