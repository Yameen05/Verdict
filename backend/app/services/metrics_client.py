"""Financial-metrics client backed by yfinance.

yfinance scrapes Yahoo Finance and exposes the result as a sync `Ticker.info`
dict. We pull a fixed subset of fields and convert to a plain dataclass to
keep the agent decoupled from the underlying library.

Sync calls are wrapped in `asyncio.to_thread` by the agent layer.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import yfinance as yf

from app.observability.logging import get_logger

log = get_logger(__name__)


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


@dataclass(slots=True)
class PriceBar:
    """One OHLCV candle for the stock viewer."""

    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None


PRICE_HISTORY_RANGES: dict[str, str] = {
    "1D": "1d",
    "5D": "5d",
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "5Y": "5y",
}

PRICE_HISTORY_INTERVALS: dict[str, str] = {
    "1M": "1m",
    "5M": "5m",
    "15M": "15m",
    "1H": "1h",
    "1D": "1d",
    "1W": "1wk",
}


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


def _timestamp_iso(ts: Any) -> str:
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    if hasattr(ts, "isoformat"):
        return str(ts.isoformat()).replace("+00:00", "Z")
    return str(ts)


def _resolve_history_window(range_key: str, interval_key: str) -> tuple[str, str, str]:
    """Return (period, yfinance interval, resolved interval key).

    Yahoo restricts fine-grained intervals to shorter periods. When a user asks
    for an interval that is too dense for a long range, keep the range and
    promote the interval to the nearest practical value.
    """
    range_key = range_key.strip().upper()
    interval_key = interval_key.strip().upper()
    if range_key not in PRICE_HISTORY_RANGES:
        allowed = ", ".join(PRICE_HISTORY_RANGES)
        raise MetricsClientError(f"Unsupported price range {range_key}; use {allowed}")
    if interval_key not in PRICE_HISTORY_INTERVALS:
        allowed = ", ".join(PRICE_HISTORY_INTERVALS)
        raise MetricsClientError(f"Unsupported price interval {interval_key}; use {allowed}")

    resolved = interval_key
    if interval_key == "1M" and range_key not in {"1D", "5D"}:
        resolved = "5M"
    if interval_key in {"1M", "5M"} and range_key in {"6M", "1Y"}:
        resolved = "1H"
    if interval_key in {"1M", "5M", "15M", "1H"} and range_key == "5Y":
        resolved = "1D"

    return PRICE_HISTORY_RANGES[range_key], PRICE_HISTORY_INTERVALS[resolved], resolved


def _yfinance_history(ticker: str, period: str, interval: str) -> list[PriceBar]:
    """Primary source. Raises MetricsClientError on failure or empty result."""
    try:
        history = yf.Ticker(ticker).history(
            period=period,
            interval=interval,
            auto_adjust=True,
        )
    except Exception as e:  # noqa: BLE001 - yfinance has unstable internals
        raise MetricsClientError(f"yfinance price history failed for {ticker}: {e}") from e

    if getattr(history, "empty", False):
        raise MetricsClientError(f"No price history available for {ticker}")

    bars: list[PriceBar] = []
    for ts, row in history.iterrows():
        open_ = _coerce_float(row.get("Open"))
        high = _coerce_float(row.get("High"))
        low = _coerce_float(row.get("Low"))
        close = _coerce_float(row.get("Close"))
        if open_ is None or high is None or low is None or close is None:
            continue
        volume_float = _coerce_float(row.get("Volume"))
        bars.append(
            PriceBar(
                time=_timestamp_iso(ts),
                open=round(open_, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=int(volume_float) if volume_float is not None else None,
            )
        )

    if not bars:
        raise MetricsClientError(f"No usable price history available for {ticker}")
    return bars


# --- Secondary price source: Stooq (free, no API key, daily/weekly only) ---
STOOQ_URL = "https://stooq.com/q/d/l/"
_STOOQ_INTERVALS: dict[str, str] = {"1D": "d", "1W": "w"}
_RANGE_CUTOFF_DAYS: dict[str, int] = {
    "1D": 4, "5D": 8, "1M": 32, "3M": 95, "6M": 190, "1Y": 372, "5Y": 1835,
}


def _stooq_symbol(ticker: str) -> str:
    sym = ticker.strip().lower()
    return sym if "." in sym else f"{sym}.us"


def fetch_stooq_history(ticker: str, stooq_interval: str, cutoff_days: int) -> list[PriceBar]:
    """Daily/weekly OHLCV from Stooq as a fallback when Yahoo is unavailable.

    Stooq returns full history as CSV (Date,Open,High,Low,Close,Volume). We keep
    only rows within `cutoff_days` of today so the range roughly matches the UI.
    Returns [] on any failure — the caller decides whether to surface an error.
    """
    params = {"s": _stooq_symbol(ticker), "i": stooq_interval}
    try:
        resp = httpx.get(STOOQ_URL, params=params, timeout=15.0)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001 - network/HTTP issues → let caller fall through
        return []

    cutoff = datetime.now(UTC).date() - timedelta(days=cutoff_days)
    bars: list[PriceBar] = []
    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        raw_date = (row.get("Date") or "").strip()
        try:
            day = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < cutoff:
            continue
        open_ = _coerce_float(row.get("Open"))
        high = _coerce_float(row.get("High"))
        low = _coerce_float(row.get("Low"))
        close = _coerce_float(row.get("Close"))
        if open_ is None or high is None or low is None or close is None:
            continue
        volume_float = _coerce_float(row.get("Volume"))
        bars.append(
            PriceBar(
                time=f"{raw_date}T00:00:00Z",
                open=round(open_, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=int(volume_float) if volume_float is not None else None,
            )
        )
    return bars


def fetch_price_history(
    ticker: str,
    range_key: str = "1M",
    interval_key: str = "1D",
) -> tuple[list[PriceBar], str]:
    """OHLCV history for the stock viewer.

    Yahoo is the primary source. For daily/weekly resolutions we fall back to
    Stooq when Yahoo fails or rate-limits, so the chart, backtest, and timing
    agent keep working. Intraday resolutions remain Yahoo-only.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise MetricsClientError("Empty ticker")
    period, interval, resolved_interval = _resolve_history_window(range_key, interval_key)

    try:
        bars = _yfinance_history(ticker, period, interval)
    except MetricsClientError as yf_err:
        stooq_interval = _STOOQ_INTERVALS.get(resolved_interval)
        if stooq_interval is None:
            raise
        cutoff = _RANGE_CUTOFF_DAYS.get(range_key.strip().upper(), 372)
        fallback = fetch_stooq_history(ticker, stooq_interval, cutoff)
        if not fallback:
            raise yf_err
        log.info("price_history_stooq_fallback", extra={"ticker": ticker})
        return fallback, resolved_interval

    return bars, resolved_interval


def fetch_latest_price_bar(ticker: str, interval_key: str = "1M") -> tuple[PriceBar, str]:
    """Latest intraday bar for live chart polling."""
    bars, resolved_interval = fetch_price_history(ticker, "1D", interval_key)
    return bars[-1], resolved_interval


def fetch_days_to_earnings(ticker: str) -> int | None:
    """Calendar days until the next earnings date, or None if unknown.

    Best-effort via yfinance's `.calendar` (no API key). The single most useful
    timing signal — buying right before earnings is a coin-flip on a gap. Any
    failure returns None so the timing agent simply omits the signal.
    """
    from datetime import date

    try:
        cal = yf.Ticker(ticker.strip().upper()).calendar
    except Exception:  # noqa: BLE001 - yfinance internals are unstable
        return None

    dates: list[Any] = []
    if isinstance(cal, dict):
        raw = cal.get("Earnings Date") or cal.get("Earnings High") or []
        dates = raw if isinstance(raw, list) else [raw]

    today = date.today()
    upcoming: list[int] = []
    for d in dates:
        # datetime/pandas Timestamp expose .date(); a plain date is used as-is.
        to_date = getattr(d, "date", None)
        day = to_date() if callable(to_date) else d
        if isinstance(day, date):
            delta = (day - today).days
            if delta >= 0:
                upcoming.append(delta)
    return min(upcoming) if upcoming else None
