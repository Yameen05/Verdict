"""Day-trade desk endpoints — intraday multi-agent signals and the scanner."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.cache import TTLCache
from app.services.daytrade import (
    DayTradeError,
    DayTradeSignal,
    ScanResponse,
    assess_daytrade,
    scan_daytrade,
)

router = APIRouter()

_signal_cache: TTLCache[DayTradeSignal] = TTLCache(60)  # a 1-minute bar's lifetime
_scan_cache: TTLCache[ScanResponse] = TTLCache(180)


def _validate_ticker(raw: str) -> str:
    ticker = (raw or "").strip().upper()
    if not ticker or len(ticker) > 10 or not ticker.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid ticker")
    return ticker


@router.get("/scan", response_model=ScanResponse)
async def scan() -> ScanResponse:
    """Rules-only sweep of liquid day-trading names, strongest setups first."""

    async def factory() -> ScanResponse:
        return await scan_daytrade()

    return await _scan_cache.get_or_set("scan", factory)


@router.get("/{ticker}/signal", response_model=DayTradeSignal)
async def signal(ticker: str) -> DayTradeSignal:
    """Full multi-agent intraday assessment for one ticker."""
    ticker = _validate_ticker(ticker)

    async def factory() -> DayTradeSignal:
        return await assess_daytrade(ticker)

    try:
        return await _signal_cache.get_or_set(ticker, factory)
    except DayTradeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
