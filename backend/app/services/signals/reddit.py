"""Reddit retail sentiment from public search JSON.

Reddit's official API is OAuth-based. For a no-key setup, this uses the public
listing JSON endpoint as best-effort context and falls back silently if Reddit
blocks anonymous requests.
"""

from __future__ import annotations

import re

from app.config import get_settings
from app.services.signals.base import get_json
from app.services.signals.types import RetailSentiment

SEARCH_URL = "https://www.reddit.com/search.json"

_BULLISH = {
    "buy",
    "bought",
    "calls",
    "call",
    "bull",
    "bullish",
    "moon",
    "breakout",
    "undervalued",
    "beat",
    "beats",
    "long",
    "hold",
    "holding",
    "strong",
}
_BEARISH = {
    "sell",
    "sold",
    "puts",
    "put",
    "bear",
    "bearish",
    "crash",
    "overvalued",
    "miss",
    "misses",
    "short",
    "dump",
    "weak",
    "bagholder",
}
_WORD_RE = re.compile(r"[A-Za-z']+")


def _post_score(text: str) -> int:
    words = {w.lower().strip("'") for w in _WORD_RE.findall(text)}
    pos = len(words & _BULLISH)
    neg = len(words & _BEARISH)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


def _label(score: float, sample: int) -> str:
    if sample == 0:
        return "n/a"
    if score >= 0.25:
        return "bullish"
    if score <= -0.25:
        return "bearish"
    return "mixed"


async def fetch_sentiment(ticker: str) -> RetailSentiment | None:
    settings = get_settings()
    if not settings.reddit_enabled:
        return None
    data = await get_json(
        SEARCH_URL,
        params={
            "q": f"${ticker} OR {ticker} stock",
            "sort": "new",
            "t": "week",
            "limit": 25,
        },
        headers={"User-Agent": settings.reddit_user_agent},
    )
    if not isinstance(data, dict):
        return None
    children = ((data.get("data") or {}).get("children") or [])
    bullish = 0
    bearish = 0
    sample = 0
    for child in children:
        post = child.get("data") if isinstance(child, dict) else None
        if not isinstance(post, dict):
            continue
        title = str(post.get("title") or "")
        body = str(post.get("selftext") or "")
        score = _post_score(f"{title} {body}")
        if score > 0:
            bullish += 1
            sample += 1
        elif score < 0:
            bearish += 1
            sample += 1
    if sample == 0:
        return None
    score = (bullish - bearish) / sample
    return RetailSentiment(
        bullish=bullish,
        bearish=bearish,
        sample=sample,
        score=round(score, 3),
        label=_label(score, sample),
        source="reddit",
    )
