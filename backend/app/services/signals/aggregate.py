"""Aggregate optional market-signal providers into one object."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

from app.config import get_settings
from app.observability.logging import get_logger
from app.services.cache import TTLCache
from app.services.signals.alphavantage import fetch_fundamentals, fetch_intraday_quote
from app.services.signals.finnhub import (
    fetch_analyst_ratings,
    fetch_earnings_days,
)
from app.services.signals.finnhub import (
    fetch_quote as fetch_finnhub_quote,
)
from app.services.signals.fred import fetch_macro_regime
from app.services.signals.polygon import fetch_previous_close, fetch_snapshot
from app.services.signals.reddit import fetch_sentiment as fetch_reddit_sentiment
from app.services.signals.stocktwits import fetch_sentiment as fetch_stocktwits_sentiment
from app.services.signals.tiingo import fetch_daily_quote, fetch_iex_quote
from app.services.signals.types import MarketSignals, RetailSentiment

log = get_logger(__name__)
T = TypeVar("T")

_cache: TTLCache[MarketSignals] | None = None
_cache_ttl: int | None = None


def _get_cache() -> TTLCache[MarketSignals] | None:
    global _cache, _cache_ttl
    ttl = get_settings().signals_cache_seconds
    if ttl <= 0:
        return None
    if _cache is None or _cache_ttl != ttl:
        _cache = TTLCache(ttl)
        _cache_ttl = ttl
    return _cache


async def _safe(name: str, awaitable: Awaitable[T | None]) -> T | None:
    try:
        return await awaitable
    except Exception as e:  # noqa: BLE001 - providers are optional context
        log.info("market_signal_failed", extra={"provider": name, "reason": str(e)[:120]})
        return None


def _retail_label(score: float, sample: int) -> str:
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


def _combine_retail(items: list[RetailSentiment | None]) -> RetailSentiment | None:
    usable = [i for i in items if i is not None and i.sample > 0]
    if not usable:
        return None
    sample = sum(i.sample for i in usable)
    bullish = sum(i.bullish for i in usable)
    bearish = sum(i.bearish for i in usable)
    weighted = sum(i.score * i.sample for i in usable) / sample
    sources = "+".join(i.source for i in usable)
    return RetailSentiment(
        bullish=bullish,
        bearish=bearish,
        sample=sample,
        score=round(weighted, 3),
        label=_retail_label(weighted, sample),
        source=sources,
    )


async def _gather_uncached(ticker: str) -> MarketSignals:
    ticker = ticker.strip().upper()
    settings = get_settings()
    (
        analyst,
        earnings_days,
        finnhub_quote,
        fundamentals,
        alpha_quote,
        polygon_snapshot,
        polygon_prev,
        tiingo_daily,
        tiingo_iex,
        macro,
        stocktwits,
        reddit,
    ) = await asyncio.gather(
        _safe("finnhub:recommendation", fetch_analyst_ratings(ticker)),
        _safe("finnhub:earnings", fetch_earnings_days(ticker)),
        _safe("finnhub:quote", fetch_finnhub_quote(ticker)),
        _safe("alphavantage:fundamentals", fetch_fundamentals(ticker)),
        _safe("alphavantage:intraday", fetch_intraday_quote(ticker)),
        _safe("polygon:snapshot", fetch_snapshot(ticker)),
        _safe("polygon:prev_close", fetch_previous_close(ticker)),
        _safe("tiingo:eod", fetch_daily_quote(ticker)),
        _safe("tiingo:iex", fetch_iex_quote(ticker)),
        _safe("fred:macro", fetch_macro_regime()),
        _safe("stocktwits:sentiment", fetch_stocktwits_sentiment(ticker)),
        _safe("reddit:sentiment", fetch_reddit_sentiment(ticker)),
    )

    quotes = [
        q
        for q in (finnhub_quote, alpha_quote, polygon_snapshot, polygon_prev, tiingo_daily, tiingo_iex)
        if q is not None and q.price is not None
    ]
    retail = _combine_retail([stocktwits, reddit])
    sources_used: list[str] = []
    if analyst is not None or earnings_days is not None or finnhub_quote is not None:
        sources_used.append("finnhub")
    if fundamentals is not None or alpha_quote is not None:
        sources_used.append("alphavantage")
    if polygon_snapshot is not None or polygon_prev is not None:
        sources_used.append("polygon")
    if tiingo_daily is not None or tiingo_iex is not None:
        sources_used.append("tiingo")
    if macro is not None:
        sources_used.append("fred")
    if stocktwits is not None:
        sources_used.append("stocktwits")
    if reddit is not None:
        sources_used.append("reddit")

    return MarketSignals(
        ticker=ticker,
        analyst=analyst,
        retail=retail,
        macro=macro,
        fundamentals=fundamentals,
        quotes=quotes,
        earnings_days=earnings_days,
        sources_used=sources_used,
        sources_available=settings.signal_sources_configured,
    )


async def gather_market_signals(ticker: str) -> MarketSignals:
    ticker = ticker.strip().upper()
    cache = _get_cache()
    if cache is None:
        return await _gather_uncached(ticker)
    return await cache.get_or_set(ticker, lambda: _gather_uncached(ticker))


def reset_signal_cache() -> None:
    global _cache
    if _cache is not None:
        _cache.clear()
