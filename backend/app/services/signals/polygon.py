"""Polygon/Massive stock price snapshots and previous-day bars."""

from __future__ import annotations

from app.config import get_settings
from app.services.signals.base import get_json, to_float
from app.services.signals.types import QuoteSignal

BASE = "https://api.polygon.io"


async def fetch_snapshot(ticker: str) -> QuoteSignal | None:
    key = get_settings().polygon_api_key.strip()
    if not key:
        return None
    data = await get_json(
        f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
        params={"apiKey": key},
    )
    if not isinstance(data, dict):
        return None
    row = data.get("ticker") if isinstance(data.get("ticker"), dict) else data
    last_trade = row.get("lastTrade") if isinstance(row, dict) else None
    day = row.get("day") if isinstance(row, dict) else None
    prev_day = row.get("prevDay") if isinstance(row, dict) else None
    price = (
        to_float((last_trade or {}).get("p"))
        or to_float((day or {}).get("c"))
        or to_float((prev_day or {}).get("c"))
    )
    previous = to_float((prev_day or {}).get("c"))
    change_pct = ((price / previous - 1.0) * 100.0) if price and previous else None
    if price is None:
        return None
    return QuoteSignal(
        price=round(price, 4),
        change_pct=round(change_pct, 3) if change_pct is not None else None,
        source="polygon_snapshot",
    )


async def fetch_previous_close(ticker: str) -> QuoteSignal | None:
    key = get_settings().polygon_api_key.strip()
    if not key:
        return None
    data = await get_json(
        f"{BASE}/v2/aggs/ticker/{ticker}/prev",
        params={"adjusted": "true", "apiKey": key},
    )
    if not isinstance(data, dict):
        return None
    rows = data.get("results") or []
    if not rows:
        return None
    row = rows[0]
    close = to_float(row.get("c"))
    open_ = to_float(row.get("o"))
    change_pct = ((close / open_ - 1.0) * 100.0) if close and open_ else None
    if close is None:
        return None
    return QuoteSignal(
        price=round(close, 4),
        change_pct=round(change_pct, 3) if change_pct is not None else None,
        source="polygon_prev_close",
    )
