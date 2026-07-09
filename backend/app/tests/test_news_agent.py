"""Unit tests for the news agent node (LLM sentiment scoring)."""

from __future__ import annotations

import pytest

from app.agents.nodes import news_agent as news_agent_mod
from app.config import get_settings
from app.schemas.research import NewsFindings
from app.services.news_client import Article, NewsAPIError
from app.services.sentiment import ScoredArticle, SentimentError


def _articles() -> list[Article]:
    return [
        Article(
            title="Apple posts record-breaking quarterly earnings, shares surge",
            description="Strong iPhone sales drove the beat.",
            source="Reuters",
            url="u1",
            published_at="2026-05-22T12:00:00Z",
        ),
        Article(
            title="Apple invests in new manufacturing line",
            description="Bullish expansion announced.",
            source="Bloomberg",
            url="u2",
            published_at="2026-05-21T09:00:00Z",
        ),
    ]


@pytest.fixture(autouse=True)
def reset_caches():
    get_settings.cache_clear()
    news_agent_mod._reset_news_cache()
    yield
    get_settings.cache_clear()
    news_agent_mod._reset_news_cache()


async def test_news_agent_uses_yahoo_fallback_when_key_missing(monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "")
    get_settings.cache_clear()

    async def fake_lookup_company_name(_ticker, client=None):
        return "Apple Inc."

    async def fake_fetch(ticker, company_name):
        assert ticker == "AAPL"
        assert company_name == "Apple Inc."
        return _articles()

    async def fake_score(_company, articles):
        scored = [ScoredArticle(article=a, score=0.2) for a in articles]
        return 0.2, scored, "Yahoo headlines lean positive."

    monkeypatch.setattr(news_agent_mod.sec_client, "lookup_company_name", fake_lookup_company_name)
    monkeypatch.setattr(news_agent_mod, "fetch_market_articles", fake_fetch)
    monkeypatch.setattr(news_agent_mod, "score_and_summarize", fake_score)

    result = await news_agent_mod.news_agent({"ticker": "AAPL"})
    findings: NewsFindings = result["news"]
    assert findings.status == "ok"
    assert findings.error is None
    assert findings.article_count == 2
    assert findings.summary == "Yahoo headlines lean positive."


async def test_news_agent_happy_path(monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "key")

    async def fake_lookup_company_name(_ticker, client=None):
        return "Apple Inc."

    async def fake_fetch(_ticker, _company):
        return _articles()

    async def fake_score(_company, articles):
        scored = [ScoredArticle(article=a, score=0.6) for a in articles]
        return 0.6, scored, "Sentiment is broadly positive."

    monkeypatch.setattr(news_agent_mod.sec_client, "lookup_company_name", fake_lookup_company_name)
    monkeypatch.setattr(news_agent_mod, "fetch_market_articles", fake_fetch)
    monkeypatch.setattr(news_agent_mod, "score_and_summarize", fake_score)

    result = await news_agent_mod.news_agent({"ticker": "AAPL"})
    findings: NewsFindings = result["news"]
    assert findings.status == "ok"
    assert findings.article_count == 2
    assert findings.sentiment_score == pytest.approx(0.6)
    assert findings.summary == "Sentiment is broadly positive."
    # Headlines carry per-article scores so the debate can cite them.
    assert len(findings.top_headlines) == 2
    assert findings.top_headlines[0].score == pytest.approx(0.6)
    assert findings.top_headlines[0].url


async def test_news_agent_degrades_when_scoring_fails(monkeypatch):
    """Headlines still ship (score-less) when the sentiment LLM call fails."""
    monkeypatch.setenv("NEWS_API_KEY", "key")

    async def fake_lookup_company_name(_ticker, client=None):
        return "Apple Inc."

    async def fake_fetch(_ticker, _company):
        return _articles()

    async def fake_score(_company, articles):
        raise SentimentError("Sentiment LLM call failed (APIError)")

    monkeypatch.setattr(news_agent_mod.sec_client, "lookup_company_name", fake_lookup_company_name)
    monkeypatch.setattr(news_agent_mod, "fetch_market_articles", fake_fetch)
    monkeypatch.setattr(news_agent_mod, "score_and_summarize", fake_score)

    result = await news_agent_mod.news_agent({"ticker": "AAPL"})
    findings: NewsFindings = result["news"]
    assert findings.status == "ok"
    assert findings.sentiment_score is None
    assert "sentiment scoring unavailable" in (findings.summary or "")
    assert len(findings.top_headlines) == 2
    assert findings.top_headlines[0].score is None


async def test_news_agent_no_articles(monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "key")

    async def fake_lookup_company_name(_ticker, client=None):
        return "Obscure Corp"

    async def fake_fetch(_ticker, _company):
        return []

    monkeypatch.setattr(news_agent_mod.sec_client, "lookup_company_name", fake_lookup_company_name)
    monkeypatch.setattr(news_agent_mod, "fetch_market_articles", fake_fetch)

    result = await news_agent_mod.news_agent({"ticker": "OBSC"})
    findings: NewsFindings = result["news"]
    assert findings.status == "ok"
    assert findings.article_count == 0
    assert findings.sentiment_score == 0.0
    assert "No recent market headlines" in (findings.summary or "")


async def test_news_agent_unknown_ticker(monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "key")

    async def boom(_ticker, client=None):
        raise ValueError("Unknown ticker: ZZZZ")

    monkeypatch.setattr(news_agent_mod.sec_client, "lookup_company_name", boom)

    result = await news_agent_mod.news_agent({"ticker": "ZZZZ"})
    findings: NewsFindings = result["news"]
    assert findings.status == "error"
    assert "Unknown ticker" in (findings.error or "")


async def test_news_agent_handles_api_error(monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "key")

    async def fake_lookup_company_name(_ticker, client=None):
        return "Apple Inc."

    async def fake_fetch(_ticker, _company):
        raise NewsAPIError("HTTP 429: rate limit")

    monkeypatch.setattr(news_agent_mod.sec_client, "lookup_company_name", fake_lookup_company_name)
    monkeypatch.setattr(news_agent_mod, "fetch_market_articles", fake_fetch)

    result = await news_agent_mod.news_agent({"ticker": "AAPL"})
    findings: NewsFindings = result["news"]
    assert findings.status == "error"
    assert "rate limit" in (findings.error or "")
