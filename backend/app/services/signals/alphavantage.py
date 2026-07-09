"""Alpha Vantage fundamentals + intraday price signal."""

from __future__ import annotations

from app.config import get_settings
from app.services.signals.base import get_json, to_float
from app.services.signals.types import Fundamentals, QuoteSignal

BASE = "https://www.alphavantage.co/query"


def _usable_payload(data: object) -> dict | None:
    if not isinstance(data, dict):
        return None
    # Alpha Vantage returns these keys for rate-limit / invalid-key / error states.
    if data.get("Note") or data.get("Information") or data.get("Error Message"):
        return None
    return data


async def fetch_fundamentals(ticker: str) -> Fundamentals | None:
    key = get_settings().alphavantage_api_key.strip()
    if not key:
        return None
    data = _usable_payload(
        await get_json(
            BASE,
            params={"function": "OVERVIEW", "symbol": ticker, "apikey": key},
        )
    )
    if not data:
        return None

    out = Fundamentals(
        pe_ratio=to_float(data.get("PERatio")),
        peg_ratio=to_float(data.get("PEGRatio")),
        profit_margin=to_float(data.get("ProfitMargin")),
        analyst_target=to_float(data.get("AnalystTargetPrice")),
        source="alphavantage",
    )
    if all(
        v is None
        for v in (out.pe_ratio, out.peg_ratio, out.profit_margin, out.analyst_target)
    ):
        return None
    return out


async def fetch_intraday_quote(ticker: str, interval: str = "5min") -> QuoteSignal | None:
    key = get_settings().alphavantage_api_key.strip()
    if not key:
        return None
    data = _usable_payload(
        await get_json(
            BASE,
            params={
                "function": "TIME_SERIES_INTRADAY",
                "symbol": ticker,
                "interval": interval,
                "outputsize": "compact",
                "apikey": key,
            },
        )
    )
    if not data:
        return None

    series = data.get(f"Time Series ({interval})")
    if not isinstance(series, dict) or not series:
        return None
    times = sorted(series.keys(), reverse=True)
    latest = series.get(times[0]) or {}
    previous = series.get(times[1]) or {} if len(times) > 1 else {}
    price = to_float(latest.get("4. close"))
    prev = to_float(previous.get("4. close"))
    change_pct = ((price / prev - 1.0) * 100.0) if price and prev else None
    if price is None:
        return None
    return QuoteSignal(
        price=round(price, 4),
        change_pct=round(change_pct, 3) if change_pct is not None else None,
        source="alphavantage_intraday",
    )
