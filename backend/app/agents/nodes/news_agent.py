"""News & Sentiment agent — Phase 3.

Resolves the ticker to a company name via the cached SEC ticker index, fetches
recent headlines from NewsAPI, scores aggregate sentiment with VADER, and asks
the configured chat model for a short narrative summary.

Skips cleanly when NEWS_API_KEY is unset so the rest of the research pipeline
still runs.
"""

from __future__ import annotations

from functools import lru_cache

from openai import AsyncOpenAI

from app.agents.state import ResearchState
from app.config import get_settings
from app.observability.cost import record_chat
from app.observability.logging import get_logger
from app.schemas.research import NewsFindings
from app.services import sec_client
from app.services.cache import TTLCache
from app.services.llm import make_llm_client
from app.services.news_client import Article, NewsAPIError, fetch_recent_articles
from app.services.sentiment import score_articles

log = get_logger(__name__)

_NEWS_TTL_SECONDS = 300  # 5 minutes
_articles_cache: TTLCache[list[Article]] = TTLCache(_NEWS_TTL_SECONDS)


async def _cached_fetch_articles(company_name: str) -> list[Article]:
    return await _articles_cache.get_or_set(
        company_name, lambda: fetch_recent_articles(company_name)
    )


def _reset_news_cache() -> None:
    _articles_cache.clear()

_SUMMARY_SYSTEM = (
    "You are a financial-research assistant summarizing recent news for an "
    "investor. Given a company name, an aggregate sentiment score in [-1, 1], "
    "and a list of recent headlines, produce a single 2-3 sentence summary "
    "that captures the dominant themes and whether sentiment skews positive, "
    "negative, or mixed. No bullet points, no preamble."
)


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    return make_llm_client()


async def _summarize(
    company_name: str, aggregate: float, articles: list[Article]
) -> str:
    if not articles:
        return "No recent news articles were found."
    headlines = "\n".join(
        f"- ({a.published_at[:10]}) {a.title}" for a in articles[:15]
    )
    model = get_settings().llm_model
    resp = await _client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Company: {company_name}\n"
                    f"Aggregate sentiment: {aggregate:.3f}\n\n"
                    f"Recent headlines:\n{headlines}"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=180,
    )
    record_chat(model, resp)
    return (resp.choices[0].message.content or "").strip()


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

    aggregate, _scored = score_articles(articles)
    try:
        summary = await _summarize(company_name, aggregate, articles)
    except Exception as e:  # noqa: BLE001 - summary is best-effort
        summary = f"({len(articles)} headlines; summary generation failed: {e})"

    return {
        "news": NewsFindings(
            status="ok",
            sentiment_score=round(aggregate, 4),
            summary=summary,
            article_count=len(articles),
        )
    }
