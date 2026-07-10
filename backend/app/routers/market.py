"""Market-data endpoints for the stock viewer."""

from __future__ import annotations

import asyncio
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.db import list_recent_runs, session_scope
from app.services.assets import asset_capabilities
from app.services.backtest import BacktestResponse, compute_backtest
from app.services.cache import TTLCache
from app.services.metrics_client import (
    PRICE_HISTORY_INTERVALS,
    PRICE_HISTORY_RANGES,
    MetricsClientError,
    PriceBar,
    fetch_latest_price_bar,
    fetch_price_history,
    horizon_stats_from_closes,
)
from app.services.timing import TimingAssessment, TimingError, assess_timing

router = APIRouter()

PriceRange = Literal["1D", "5D", "1M", "3M", "6M", "1Y", "5Y"]
PriceInterval = Literal["1M", "5M", "15M", "1H", "1D", "1W"]
MAX_BACKTEST_TICKERS = 25
_history_cache: TTLCache[tuple[list[PriceBar], str]] = TTLCache(60)
_quote_cache: TTLCache[tuple[PriceBar, str]] = TTLCache(10)
_daily_cache: TTLCache[list[PriceBar]] = TTLCache(600)  # 10 min; backtest + /ranges
_timing_cache: TTLCache[TimingAssessment] = TTLCache(120)  # 2 min


class PriceBarResponse(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None


class PriceHistoryResponse(BaseModel):
    ticker: str
    range: PriceRange
    interval: PriceInterval
    requested_interval: PriceInterval
    bars: list[PriceBarResponse]


class LatestPriceResponse(BaseModel):
    ticker: str
    interval: PriceInterval
    requested_interval: PriceInterval
    bar: PriceBarResponse


class ReturnRangeRow(BaseModel):
    horizon_days: int
    label: str
    amount: float
    likely_low: float | None = None
    likely_high: float | None = None
    normal_move_pct: float | None = None
    recent_return_pct: float | None = None
    best_case: float | None = None
    best_case_pct: float | None = None
    worst_case: float | None = None
    worst_case_pct: float | None = None


class ReturnRangeResponse(BaseModel):
    ticker: str
    amount: float
    rows: list[ReturnRangeRow]
    note: str = (
        "Ranges use this asset's rolling historical moves over roughly the past "
        "year (longer holds reach further back). They show normal swing size, "
        "not a guaranteed forecast."
    )


RANGE_HORIZONS: tuple[tuple[int, str], ...] = (
    (7, "1 week"),
    (14, "2 weeks"),
    (30, "1 month"),
    (90, "3 months"),
    (365, "1 year"),
)


def _validate_ticker(raw: str) -> str:
    ticker = (raw or "").strip().upper()
    if not ticker or len(ticker) > 10 or not ticker.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid ticker")
    return ticker


def _validate_range(raw: str) -> PriceRange:
    value = (raw or "").strip().upper()
    if value not in PRICE_HISTORY_RANGES:
        allowed = ", ".join(PRICE_HISTORY_RANGES)
        raise HTTPException(status_code=400, detail=f"Invalid range. Use one of: {allowed}")
    return cast(PriceRange, value)


def _validate_interval(raw: str) -> PriceInterval:
    value = (raw or "").strip().upper()
    if value not in PRICE_HISTORY_INTERVALS:
        allowed = ", ".join(PRICE_HISTORY_INTERVALS)
        raise HTTPException(status_code=400, detail=f"Invalid interval. Use one of: {allowed}")
    return cast(PriceInterval, value)


def _bar_response(bar: PriceBar) -> PriceBarResponse:
    return PriceBarResponse(
        time=bar.time,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
    )


async def _cached_history(
    ticker: str, range_key: PriceRange, interval_key: PriceInterval
) -> tuple[list[PriceBar], str]:
    async def factory() -> tuple[list[PriceBar], str]:
        return await asyncio.to_thread(fetch_price_history, ticker, range_key, interval_key)

    return await _history_cache.get_or_set(f"{ticker}:{range_key}:{interval_key}", factory)


async def _cached_quote(ticker: str, interval_key: PriceInterval) -> tuple[PriceBar, str]:
    async def factory() -> tuple[PriceBar, str]:
        return await asyncio.to_thread(fetch_latest_price_bar, ticker, interval_key)

    return await _quote_cache.get_or_set(f"{ticker}:{interval_key}", factory)


async def _daily_history(ticker: str) -> list[PriceBar]:
    async def factory() -> list[PriceBar]:
        try:
            bars, _ = await asyncio.to_thread(fetch_price_history, ticker, "5Y", "1D")
            return bars
        except MetricsClientError:
            return []

    return await _daily_cache.get_or_set(ticker.upper(), factory)


def _reset_cache() -> None:
    _history_cache.clear()
    _quote_cache.clear()
    _daily_cache.clear()
    _timing_cache.clear()


class AssetCapabilities(BaseModel):
    ticker: str
    asset_class: str
    display_name: str | None
    has_filings: bool
    has_insiders: bool
    has_earnings: bool
    has_analyst_coverage: bool
    trades_24_7: bool
    note: str | None


@router.get("/{ticker}/capabilities", response_model=AssetCapabilities)
async def capabilities(ticker: str) -> AssetCapabilities:
    """Which evidence types exist for this asset (crypto has no SEC filings)."""
    return AssetCapabilities(**asset_capabilities(_validate_ticker(ticker)))


@router.get("/{ticker}/history", response_model=PriceHistoryResponse)
async def price_history(
    ticker: str,
    range: str = "1M",
    interval: str = "1D",
) -> PriceHistoryResponse:
    ticker = _validate_ticker(ticker)
    range_key = _validate_range(range)
    interval_key = _validate_interval(interval)
    try:
        bars, resolved_interval = await _cached_history(ticker, range_key, interval_key)
    except MetricsClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return PriceHistoryResponse(
        ticker=ticker,
        range=range_key,
        interval=cast(PriceInterval, resolved_interval),
        requested_interval=interval_key,
        bars=[_bar_response(bar) for bar in bars],
    )


@router.get("/{ticker}/quote", response_model=LatestPriceResponse)
async def latest_price(ticker: str, interval: str = "1M") -> LatestPriceResponse:
    ticker = _validate_ticker(ticker)
    interval_key = _validate_interval(interval)
    try:
        bar, resolved_interval = await _cached_quote(ticker, interval_key)
    except MetricsClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return LatestPriceResponse(
        ticker=ticker,
        interval=cast(PriceInterval, resolved_interval),
        requested_interval=interval_key,
        bar=_bar_response(bar),
    )


@router.get("/{ticker}/timing", response_model=TimingAssessment)
async def timing(ticker: str, horizon: int = 14) -> TimingAssessment:
    """Read the chart + news and suggest whether to buy now, wait, or accumulate."""
    ticker = _validate_ticker(ticker)
    horizon = min(max(horizon, 1), 365)

    async def factory() -> TimingAssessment:
        return await assess_timing(ticker, horizon)

    try:
        return await _timing_cache.get_or_set(f"{ticker}:{horizon}", factory)
    except TimingError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/{ticker}/ranges", response_model=ReturnRangeResponse)
async def return_ranges(ticker: str, amount: float = 200.0) -> ReturnRangeResponse:
    """Dollar return ranges for common holding windows."""
    ticker = _validate_ticker(ticker)
    amount = min(max(float(amount), 1.0), 1_000_000.0)

    closes = [bar.close for bar in await _daily_history(ticker)]
    if not closes:
        raise HTTPException(
            status_code=502, detail=f"No price history available for {ticker}"
        )

    def row(days: int, label: str) -> ReturnRangeRow:
        try:
            stats = horizon_stats_from_closes(closes, days)
        except MetricsClientError:
            return ReturnRangeRow(horizon_days=days, label=label, amount=round(amount, 2))
        swing = stats.typical_swing_pct
        return ReturnRangeRow(
            horizon_days=days,
            label=label,
            amount=round(amount, 2),
            likely_low=round(amount * (1 - swing / 100), 2)
            if swing is not None
            else None,
            likely_high=round(amount * (1 + swing / 100), 2)
            if swing is not None
            else None,
            normal_move_pct=swing,
            recent_return_pct=stats.recent_return_pct,
            best_case=round(amount * (1 + stats.best_window_pct / 100), 2)
            if stats.best_window_pct is not None
            else None,
            best_case_pct=stats.best_window_pct,
            worst_case=round(amount * (1 + stats.worst_window_pct / 100), 2)
            if stats.worst_window_pct is not None
            else None,
            worst_case_pct=stats.worst_window_pct,
        )

    rows = [row(days, label) for days, label in RANGE_HORIZONS]
    return ReturnRangeResponse(ticker=ticker, amount=round(amount, 2), rows=rows)


@router.get("/backtest", response_model=BacktestResponse)
async def backtest(
    limit: int = 200,
    session: AsyncSession = Depends(session_scope),
) -> BacktestResponse:
    """Grade every past verdict at the horizon it committed to (see services/backtest)."""
    rows = await list_recent_runs(session, limit=min(max(limit, 1), 500))

    scorable = [r for r in rows if r.price_at_run and r.recommendation != "Pending"]
    tickers = list(dict.fromkeys(r.ticker.upper() for r in scorable))[:MAX_BACKTEST_TICKERS]
    fetched = await asyncio.gather(*(_daily_history(t) for t in tickers))
    histories = dict(zip(tickers, fetched, strict=True))

    return compute_backtest(rows, histories)
