"""Unit tests for the batched LLM sentiment scorer."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services import sentiment as sentiment_mod
from app.services.news_client import Article
from app.services.sentiment import SentimentError, score_and_summarize


def _article(title: str) -> Article:
    return Article(title=title, description="", source="", url="", published_at="")


def _fake_openai_returning(content: str):
    class _C:
        async def create(self, **_kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    class _Chat:
        completions = _C()

    return SimpleNamespace(chat=_Chat())


@pytest.fixture(autouse=True)
def reset_client():
    if hasattr(sentiment_mod._client, "cache_clear"):
        sentiment_mod._client.cache_clear()
    yield
    if hasattr(sentiment_mod._client, "cache_clear"):
        sentiment_mod._client.cache_clear()


async def test_empty_articles_returns_neutral():
    agg, scored, summary = await score_and_summarize("Apple Inc.", [])
    assert agg == 0.0
    assert scored == []
    assert "No recent articles" in summary


async def test_scores_and_summary_parsed(monkeypatch):
    payload = json.dumps({"scores": [0.8, -0.4, 5.0], "summary": "Mixed coverage."})
    monkeypatch.setattr(sentiment_mod, "_client", lambda: _fake_openai_returning(payload))

    arts = [_article("beat"), _article("miss"), _article("out of range")]
    agg, scored, summary = await score_and_summarize("Apple Inc.", arts)

    assert scored[0].score == pytest.approx(0.8)
    assert scored[1].score == pytest.approx(-0.4)
    assert scored[2].score == pytest.approx(1.0)  # clamped
    assert agg == pytest.approx((0.8 - 0.4 + 1.0) / 3)
    assert summary == "Mixed coverage."


async def test_missing_scores_default_to_neutral(monkeypatch):
    payload = json.dumps({"scores": [0.5], "summary": "Thin."})
    monkeypatch.setattr(sentiment_mod, "_client", lambda: _fake_openai_returning(payload))

    arts = [_article("a"), _article("b")]
    agg, scored, _ = await score_and_summarize("Apple Inc.", arts)
    assert scored[1].score == 0.0
    assert agg == pytest.approx(0.25)


async def test_unparseable_output_raises(monkeypatch):
    monkeypatch.setattr(
        sentiment_mod, "_client", lambda: _fake_openai_returning("not json")
    )
    with pytest.raises(SentimentError):
        await score_and_summarize("Apple Inc.", [_article("a")])
