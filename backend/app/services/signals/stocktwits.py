"""StockTwits retail sentiment."""

from __future__ import annotations

from app.config import get_settings
from app.services.signals.base import get_json
from app.services.signals.types import RetailSentiment

BASE = "https://api.stocktwits.com/api/2/streams/symbol"


def _label(score: float, sample: int) -> str:
    if sample == 0:
        return "n/a"
    if score >= 0.35:
        return "very bullish"
    if score >= 0.12:
        return "bullish"
    if score <= -0.35:
        return "very bearish"
    if score <= -0.12:
        return "bearish"
    return "mixed"


async def fetch_sentiment(ticker: str) -> RetailSentiment | None:
    if not get_settings().stocktwits_enabled:
        return None
    data = await get_json(
        f"{BASE}/{ticker}.json",
        headers={"User-Agent": get_settings().reddit_user_agent},
    )
    if not isinstance(data, dict):
        return None
    bullish = 0
    bearish = 0
    for msg in data.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        sentiment = ((msg.get("entities") or {}).get("sentiment") or {}).get("basic")
        if sentiment == "Bullish":
            bullish += 1
        elif sentiment == "Bearish":
            bearish += 1
    sample = bullish + bearish
    if sample == 0:
        return None
    score = (bullish - bearish) / sample
    return RetailSentiment(
        bullish=bullish,
        bearish=bearish,
        sample=sample,
        score=round(score, 3),
        label=_label(score, sample),
        source="stocktwits",
    )
