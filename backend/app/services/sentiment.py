"""LLM-based sentiment scoring for financial news headlines.

Replaces VADER. A general-purpose social-media lexicon misreads finance
language constantly — "crushes estimates" scores negative, "cuts losses"
scores wrong, "beats" is ambiguous. One batched cheap-LLM call scores every
headline in context AND writes the narrative summary, so this costs one
request per run and fractions of a cent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from openai import AsyncOpenAI, OpenAIError

from app.config import get_settings
from app.observability.cost import record_chat
from app.observability.logging import get_logger
from app.services.llm import make_llm_client
from app.services.news_client import Article

log = get_logger(__name__)


class SentimentError(RuntimeError):
    pass


@dataclass(slots=True)
class ScoredArticle:
    article: Article
    score: float  # [-1, 1]


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    return make_llm_client()


_SYSTEM = """You score financial news sentiment for an investor in one company.
You receive the company name and a numbered list of recent headlines (with
descriptions). For EACH headline, assign a sentiment score in [-1.0, 1.0]
from the perspective of a shareholder of that company:
  +1.0 clearly bullish for the stock, 0 neutral/irrelevant, -1.0 clearly bearish.
Score financial meaning, not word polarity — "crushes estimates" is positive,
"cuts guidance" is negative, a competitor's failure may be positive.

Also write a 2-3 sentence narrative summary of the dominant themes and whether
coverage skews positive, negative, or mixed. No bullet points.

Return ONLY JSON: {"scores": [s0, s1, ...] (one per headline, same order),
"summary": "..."}"""


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


async def score_and_summarize(
    company_name: str, articles: list[Article]
) -> tuple[float | None, list[ScoredArticle], str]:
    """Return (aggregate_score, per-article scores, narrative summary).

    Raises SentimentError when the LLM call fails or returns garbage — the
    caller decides how to degrade.
    """
    if not articles:
        return 0.0, [], f"No recent articles found for {company_name}."

    lines = "\n".join(
        f"{i}. ({a.published_at[:10]}) {a.title}"
        + (f" — {a.description[:200]}" if a.description else "")
        for i, a in enumerate(articles)
    )
    model = get_settings().llm_model
    try:
        resp = await _client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Company: {company_name}\n\nHeadlines:\n{lines}"},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except OpenAIError as e:
        raise SentimentError(f"Sentiment LLM call failed ({type(e).__name__})") from e
    record_chat(model, resp)

    try:
        data = json.loads(resp.choices[0].message.content or "{}")
        raw_scores = data.get("scores") or []
        summary = str(data.get("summary", "")).strip()
    except json.JSONDecodeError as e:
        raise SentimentError(f"Sentiment output unparseable: {e}") from e

    scored: list[ScoredArticle] = []
    for i, article in enumerate(articles):
        try:
            score = _clamp(float(raw_scores[i]))
        except (IndexError, TypeError, ValueError):
            score = 0.0
        scored.append(ScoredArticle(article=article, score=score))

    if not scored:
        raise SentimentError("Sentiment model returned no scores")

    aggregate = _clamp(sum(s.score for s in scored) / len(scored))
    return aggregate, scored, summary or "No summary produced."
