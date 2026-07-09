"""Unit tests for news_client. NewsAPI HTTP is mocked."""

from __future__ import annotations

import re

import pytest
from pytest_httpx import HTTPXMock

from app.config import get_settings
from app.services import news_client

_URL_RE = re.compile(r"^https://newsapi\.org/v2/everything")

@pytest.fixture(autouse=True)
def set_news_key(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NEWS_API_KEY", "test-key-123")
    yield
    get_settings.cache_clear()


async def test_fetch_recent_articles_happy_path(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=_URL_RE,
        json={
            "status": "ok",
            "totalResults": 2,
            "articles": [
                {
                    "title": "Apple announces record earnings",
                    "description": "Strong iPhone sales.",
                    "source": {"name": "Reuters"},
                    "url": "https://example.com/1",
                    "publishedAt": "2026-05-22T12:00:00Z",
                },
                {
                    "title": "Apple faces antitrust scrutiny",
                    "description": "EU probe widens.",
                    "source": {"name": "Bloomberg"},
                    "url": "https://example.com/2",
                    "publishedAt": "2026-05-21T09:00:00Z",
                },
            ],
        },
    )
    articles = await news_client.fetch_recent_articles("Apple Inc.")
    assert len(articles) == 2
    assert articles[0].title.startswith("Apple announces")
    assert articles[0].source == "Reuters"


async def test_fetch_drops_empty_titles(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=_URL_RE,
        json={
            "status": "ok",
            "articles": [
                {"title": None, "description": "x", "source": {"name": "S"}},
                {"title": "valid", "description": "y", "source": {"name": "S"}},
            ],
        },
    )
    articles = await news_client.fetch_recent_articles("X")
    assert [a.title for a in articles] == ["valid"]


async def test_fetch_raises_on_http_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=_URL_RE,
        status_code=429,
        text="Rate limit",
    )
    with pytest.raises(news_client.NewsAPIError, match="429"):
        await news_client.fetch_recent_articles("X")


async def test_fetch_raises_on_api_error_body(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=_URL_RE,
        json={"status": "error", "code": "apiKeyInvalid", "message": "bad key"},
    )
    with pytest.raises(news_client.NewsAPIError, match="apiKeyInvalid"):
        await news_client.fetch_recent_articles("X")


async def test_fetch_raises_when_key_missing(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NEWS_API_KEY", "")
    with pytest.raises(news_client.NewsAPIError, match="NEWS_API_KEY"):
        await news_client.fetch_recent_articles("X")


async def test_fetch_market_articles_uses_yfinance_when_key_missing(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("NEWS_API_KEY", "")

    class _FakeTicker:
        def __init__(self, ticker: str):
            assert ticker == "NVDA"

        @property
        def news(self):
            return [
                {
                    "content": {
                        "title": "Nvidia shares rise after analyst note",
                        "summary": "Chip demand remains strong.",
                        "provider": {"displayName": "Yahoo Finance"},
                        "canonicalUrl": {"url": "https://finance.yahoo.com/news/nvda"},
                        "pubDate": "2026-07-08T13:15:00Z",
                    }
                }
            ]

    monkeypatch.setattr(news_client.yf, "Ticker", _FakeTicker)

    articles = await news_client.fetch_market_articles("NVDA", "NVIDIA Corporation")

    assert len(articles) == 1
    assert articles[0].title.startswith("Nvidia shares rise")
    assert articles[0].source == "Yahoo Finance"
    assert articles[0].published_at == "2026-07-08T13:15:00Z"
