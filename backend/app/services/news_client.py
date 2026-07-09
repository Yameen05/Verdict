"""NewsAPI.org client.

Free Developer tier:
- 100 requests/day
- 30-day article window on the `everything` endpoint
- Single endpoint we use: GET /v2/everything

Docs: https://newsapi.org/docs/endpoints/everything
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import yfinance as yf

from app.config import get_settings

NEWS_API_URL = "https://newsapi.org/v2/everything"


@dataclass(slots=True)
class Article:
    title: str
    description: str
    source: str
    url: str
    published_at: str  # ISO8601


class NewsAPIError(RuntimeError):
    pass


_GENERIC_COMPANY_WORDS = {
    "class",
    "common",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "limited",
    "ltd",
    "plc",
    "stock",
}


def _relevance_terms(ticker: str, company_name: str | None) -> list[str]:
    terms = {ticker.lower().split("-")[0].split(".")[0]}
    for word in re.findall(r"[a-z0-9]+", (company_name or "").lower()):
        if len(word) >= 3 and word not in _GENERIC_COMPANY_WORDS:
            terms.add(word)
    return sorted(terms)


def _relevant_articles(
    articles: list[Article],
    ticker: str,
    company_name: str | None,
) -> list[Article]:
    terms = _relevance_terms(ticker, company_name)
    filtered = [
        article
        for article in articles
        if any(
            term
            in f"{article.title} {article.description} {article.url}".lower()
            for term in terms
        )
    ]
    return filtered or articles


def _nested(mapping: dict[str, Any], *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _published_at(item: dict[str, Any]) -> str:
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    raw = content.get("pubDate") or item.get("pubDate")
    if isinstance(raw, str) and raw:
        return raw
    epoch = content.get("providerPublishTime") or item.get("providerPublishTime")
    if isinstance(epoch, (int, float)):
        return datetime.fromtimestamp(epoch, tz=UTC).isoformat().replace("+00:00", "Z")
    return raw if isinstance(raw, str) else ""


def _article_from_yfinance(item: dict[str, Any]) -> Article | None:
    content = item.get("content") if isinstance(item.get("content"), dict) else item
    title = str(content.get("title") or item.get("title") or "").strip()
    if not title:
        return None
    url = (
        _nested(content, "canonicalUrl", "url")
        or _nested(content, "clickThroughUrl", "url")
        or content.get("link")
        or item.get("link")
        or ""
    )
    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    return Article(
        title=title,
        description=str(
            content.get("summary")
            or content.get("description")
            or item.get("summary")
            or item.get("description")
            or ""
        ),
        source=str(provider.get("displayName") or item.get("publisher") or "Yahoo Finance"),
        url=str(url),
        published_at=_published_at(item),
    )


async def fetch_yfinance_articles(
    ticker: str,
    company_name: str | None = None,
    limit: int | None = None,
) -> list[Article]:
    """Return recent Yahoo Finance headlines through yfinance with no API key."""
    ticker = ticker.strip().upper()
    if not ticker:
        raise NewsAPIError("Empty ticker")
    limit = limit or get_settings().news_max_articles

    try:
        raw_items = await asyncio.to_thread(lambda: yf.Ticker(ticker).news or [])
    except Exception as e:  # noqa: BLE001 - yfinance has unstable internals
        raise NewsAPIError(f"Yahoo Finance news lookup failed for {ticker}: {e}") from e

    articles = []
    for item in raw_items:
        article = _article_from_yfinance(item)
        if article is not None:
            articles.append(article)
    return _relevant_articles(articles, ticker, company_name)[:limit]


async def fetch_recent_articles(
    company_name: str,
    days: int | None = None,
    limit: int | None = None,
) -> list[Article]:
    """Return up to `limit` recent articles mentioning `company_name`.

    Raises NewsAPIError if no API key configured or the request fails.
    """
    settings = get_settings()
    api_key = settings.news_api_key
    if not api_key:
        raise NewsAPIError("NEWS_API_KEY not set")

    days = days or settings.news_lookback_days
    limit = limit or settings.news_max_articles

    from_dt = datetime.now(UTC) - timedelta(days=days)
    params = {
        "q": f'"{company_name}"',  # quoted to avoid loose token matches
        "from": from_dt.strftime("%Y-%m-%d"),
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": min(limit, 100),
        "apiKey": api_key,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(NEWS_API_URL, params=params)
        if r.status_code != 200:
            raise NewsAPIError(
                f"NewsAPI HTTP {r.status_code}: {r.text[:200]}"
            )
        body = r.json()
        if body.get("status") != "ok":
            raise NewsAPIError(
                f"NewsAPI error: {body.get('code')} {body.get('message')}"
            )

    return [
        Article(
            title=a.get("title") or "",
            description=a.get("description") or "",
            source=(a.get("source") or {}).get("name") or "",
            url=a.get("url") or "",
            published_at=a.get("publishedAt") or "",
        )
        for a in (body.get("articles") or [])[:limit]
        if a.get("title")
    ]


async def fetch_market_articles(ticker: str, company_name: str) -> list[Article]:
    """Use NewsAPI when configured, otherwise fall back to yfinance news."""
    if get_settings().news_api_key:
        return await fetch_recent_articles(company_name)
    return await fetch_yfinance_articles(ticker, company_name)
