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


@dataclass(slots=True)
class HorizonStats:
    """What this asset historically does over the user's holding window.

    Computed from one year of daily closes — deterministic, no model involved.
    """

    horizon_days: int  # calendar days the user plans to hold
    recent_return_pct: float | None  # actual move over the most recent window
    typical_swing_pct: float | None  # one std-dev of rolling window returns
    best_window_pct: float | None  # best window in the past year
    worst_window_pct: float | None  # worst window in the past year


def _trading_days(calendar_days: int) -> int:
    # ~5 trading days per 7 calendar days; crypto trades daily but using the
    # same convention keeps windows comparable.
    return max(1, round(calendar_days * 5 / 7))


def fetch_horizon_stats(ticker: str, horizon_days: int) -> HorizonStats:
    """Rolling-window return stats for the user's holding period.

    Raises MetricsClientError when there isn't enough history to say anything.
    """
    ticker = ticker.strip().upper()
    try:
        history = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
        closes = [float(c) for c in history["Close"].tolist() if c == c]  # drop NaN
    except Exception as e:  # noqa: BLE001 - yfinance has unstable internals
        raise MetricsClientError(f"yfinance history failed for {ticker}: {e}") from e

    window = _trading_days(horizon_days)
    if len(closes) < window + 2:
        raise MetricsClientError(
            f"Not enough price history for {ticker} to analyze a {horizon_days}-day hold"
        )

    rolling = [
        closes[i + window] / closes[i] - 1.0 for i in range(len(closes) - window)
    ]
    mean = sum(rolling) / len(rolling)
    variance = sum((r - mean) ** 2 for r in rolling) / len(rolling)

    return HorizonStats(
        horizon_days=horizon_days,
        recent_return_pct=round((closes[-1] / closes[-1 - window] - 1.0) * 100, 2),
        typical_swing_pct=round((variance**0.5) * 100, 2),
        best_window_pct=round(max(rolling) * 100, 2),
        worst_window_pct=round(min(rolling) * 100, 2),
    )
