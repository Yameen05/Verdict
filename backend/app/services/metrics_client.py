"""Financial-metrics client backed by yfinance.

yfinance scrapes Yahoo Finance and exposes the result as a sync `Ticker.info`
dict. We pull a fixed subset of fields and convert to a plain dataclass to
keep the agent decoupled from the underlying library.

Sync calls are wrapped in `asyncio.to_thread` by the agent layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yfinance as yf


class MetricsClientError(RuntimeError):
    pass


@dataclass(slots=True)
class Metrics:
    revenue: float | None  # totalRevenue (TTM, USD)
    eps: float | None  # trailing twelve-month EPS
    pe_ratio: float | None  # trailing P/E
    profit_margin: float | None  # decimal, e.g. 0.25 = 25%
    debt_to_equity: float | None
    week_52_low: float | None
    week_52_high: float | None
    current_price: float | None = None


# yfinance dict-key -> our field name. None means "not yet populated".
_FIELD_MAP: dict[str, str] = {
    "totalRevenue": "revenue",
    "trailingEps": "eps",
    "trailingPE": "pe_ratio",
    "profitMargins": "profit_margin",
    "debtToEquity": "debt_to_equity",
    "fiftyTwoWeekLow": "week_52_low",
    "fiftyTwoWeekHigh": "week_52_high",
    "currentPrice": "current_price",
}


def _coerce_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # yfinance occasionally returns NaN; keep them out.
    if f != f:  # NaN check without importing math
        return None
    return f


def fetch_metrics(ticker: str) -> Metrics:
    """Pull the metrics subset from yfinance.

    Raises MetricsClientError if the ticker is unknown or yfinance returns an
    essentially-empty `info` dict (Yahoo's signal for "no such symbol").
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise MetricsClientError("Empty ticker")

    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as e:  # noqa: BLE001 - yfinance has unstable internals
        raise MetricsClientError(f"yfinance lookup failed for {ticker}: {e}") from e

    # Yahoo returns a near-empty dict for unknown tickers (sometimes just
    # {"trailingPegRatio": None}). Detect that by checking for any of the
    # mapped fields being present and non-null.
    if not any(info.get(k) is not None for k in _FIELD_MAP):
        raise MetricsClientError(
            f"No metrics available for {ticker} (unknown symbol or Yahoo returned empty)"
        )

    return Metrics(
        revenue=_coerce_float(info.get("totalRevenue")),
        eps=_coerce_float(info.get("trailingEps")),
        pe_ratio=_coerce_float(info.get("trailingPE")),
        profit_margin=_coerce_float(info.get("profitMargins")),
        debt_to_equity=_coerce_float(info.get("debtToEquity")),
        week_52_low=_coerce_float(info.get("fiftyTwoWeekLow")),
        week_52_high=_coerce_float(info.get("fiftyTwoWeekHigh")),
        current_price=_coerce_float(
            info.get("currentPrice") or info.get("regularMarketPrice")
        ),
    )


def fetch_price(ticker: str) -> float | None:
    """Just the latest price — used by the scoreboard to compute forward returns."""
    ticker = ticker.strip().upper()
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as e:  # noqa: BLE001 - yfinance has unstable internals
        raise MetricsClientError(f"yfinance price lookup failed for {ticker}: {e}") from e
    return _coerce_float(info.get("currentPrice") or info.get("regularMarketPrice"))
