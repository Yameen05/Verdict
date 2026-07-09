"""Typed results for external market signals."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalystRatings(BaseModel):
    strong_buy: int = 0
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_sell: int = 0
    period: str | None = None
    consensus: str = "n/a"  # Strong Buy | Buy | Hold | Sell | Strong Sell
    score: float = 0.0  # -1 (bearish) .. +1 (bullish)
    source: str = "finnhub"


class RetailSentiment(BaseModel):
    bullish: int = 0
    bearish: int = 0
    sample: int = 0
    score: float = 0.0  # -1 .. +1
    label: str = "n/a"
    source: str = "stocktwits"


class MacroRegime(BaseModel):
    fed_funds_pct: float | None = None
    cpi_yoy_pct: float | None = None
    unemployment_pct: float | None = None
    yield_spread_10y_2y: float | None = None
    regime: str = "n/a"  # supportive | neutral | restrictive
    note: str = ""
    source: str = "fred"


class Fundamentals(BaseModel):
    pe_ratio: float | None = None
    peg_ratio: float | None = None
    profit_margin: float | None = None
    analyst_target: float | None = None
    source: str = "alphavantage"


class QuoteSignal(BaseModel):
    price: float | None = None
    change_pct: float | None = None
    source: str


class MarketSignals(BaseModel):
    ticker: str
    analyst: AnalystRatings | None = None
    retail: RetailSentiment | None = None
    macro: MacroRegime | None = None
    fundamentals: Fundamentals | None = None
    quotes: list[QuoteSignal] = Field(default_factory=list)
    earnings_days: int | None = None  # from Finnhub calendar (preferred)
    sources_used: list[str] = Field(default_factory=list)
    sources_available: list[str] = Field(default_factory=list)
