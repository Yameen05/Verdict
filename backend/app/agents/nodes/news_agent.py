"""News & Sentiment agent.

Resolves the ticker to a company name via the cached SEC ticker index, fetches
recent headlines from NewsAPI, and scores per-headline + aggregate sentiment
with one batched LLM call that also writes the narrative summary.

Skips cleanly when NEWS_API_KEY is unset so the rest of the research pipeline
still runs. If sentiment scoring fails, the headlines still ship (score-less)
so the debate can cite them.
"""

from __future__ import annotations

from app.agents.state import ResearchState
from app.config import get_settings
from app.observability.logging import get_logger
from app.schemas.research import Headline, NewsFindings
from app.services import sec_client
from app.services.cache import TTLCache
from app.services.news_client import Article, NewsAPIError, fetch_recent_articles
from app.services.sentiment import ScoredArticle, SentimentError, score_and_summarize

log = get_logger(__name__)

_NEWS_TTL_SECONDS = 300  # 5 minutes
_articles_cache: TTLCache[list[Article]] = TTLCache(_NEWS_TTL_SECONDS)

TOP_HEADLINES = 8


async def _cached_fetch_articles(company_name: str) -> list[Article]:
    return await _articles_cache.get_or_set(
        company_name, lambda: fetch_recent_articles(company_name)
    )


def _reset_news_cache() -> None:
    _articles_cache.clear()


def _headlines(scored: list[ScoredArticle]) -> list[Headline]:
    # Most opinionated first — strong signals are what the debate cites.
    ranked = sorted(scored, key=lambda s: abs(s.score), reverse=True)[:TOP_HEADLINES]
    return [
        Headline(
            title=s.article.title,
            source=s.article.source,
            published_at=s.article.published_at,
            url=s.article.url,
            score=round(s.score, 2),
        )
        for s in ranked
    ]


async def news_agent(state: ResearchState) -> dict:
    ticker = state["ticker"]

    if not get_settings().news_api_key:
        return {
            "news": NewsFindings(
                status="skipped",
                error="NEWS_API_KEY not set; news agent skipped.",
            )
        }

    try:
        company_name = await sec_client.lookup_company_name(ticker)
    except ValueError as e:
        return {"news": NewsFindings(status="error", error=str(e))}

    try:
        articles = await _cached_fetch_articles(company_name)
    except NewsAPIError as e:
        return {"news": NewsFindings(status="error", error=str(e))}

    if not articles:
        return {
            "news": NewsFindings(
                status="ok",
                sentiment_score=0.0,
                summary=f"No recent articles found for {company_name}.",
                article_count=0,
            )
        }

    try:
        aggregate, scored, summary = await score_and_summarize(company_name, articles)
    except SentimentError as e:
        # Headlines are still usable evidence even without scores.
        log.warning("sentiment_scoring_failed", extra={"ticker": ticker, "reason": str(e)})
        return {
            "news": NewsFindings(
                status="ok",
                sentiment_score=None,
                summary=f"({len(articles)} recent headlines; sentiment scoring unavailable: {e})",
                article_count=len(articles),
                top_headlines=[
                    Headline(
                        title=a.title,
                        source=a.source,
                        published_at=a.published_at,
                        url=a.url,
                    )
                    for a in articles[:TOP_HEADLINES]
                ],
            )
        }

    return {
        "news": NewsFindings(
            status="ok",
            sentiment_score=round(aggregate, 4) if aggregate is not None else None,
            summary=summary,
            article_count=len(articles),
            top_headlines=_headlines(scored),
        )
    }
