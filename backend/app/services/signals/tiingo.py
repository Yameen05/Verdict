"""Tiingo EOD and IEX quote signals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.services.signals.base import get_json, to_float
from app.services.signals.types import QuoteSignal

BASE = "https://api.tiingo.com"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Token {token}"}


async def fetch_daily_quote(ticker: str) -> QuoteSignal | None:
    token = get_settings().tiingo_api_key.strip()
    if not token:
        return None
    start = (datetime.now(UTC).date() - timedelta(days=10)).isoformat()
    data = await get_json(
        f"{BASE}/tiingo/daily/{ticker.lower()}/prices",
        params={"startDate": start},
        headers=_headers(token),
    )
    if not isinstance(data, list) or not data:
        return None
    rows = sorted(data, key=lambda r: str(r.get("date", "")))
    latest = rows[-1]
    previous = rows[-2] if len(rows) > 1 else {}
    price = to_float(latest.get("adjClose")) or to_float(latest.get("close"))
    prev = to_float(previous.get("adjClose")) or to_float(previous.get("close"))
    change_pct = ((price / prev - 1.0) * 100.0) if price and prev else None
    if price is None:
        return None
    return QuoteSignal(
        price=round(price, 4),
        change_pct=round(change_pct, 3) if change_pct is not None else None,
        source="tiingo_eod",
    )


async def fetch_iex_quote(ticker: str) -> QuoteSignal | None:
    token = get_settings().tiingo_api_key.strip()
    if not token:
        return None
    data = await get_json(f"{BASE}/iex/{ticker.lower()}", headers=_headers(token))
    if isinstance(data, list):
        row = data[0] if data else None
    elif isinstance(data, dict):
        row = data
    else:
        row = None
    if not isinstance(row, dict):
        return None
    price = (
        to_float(row.get("tngoLast"))
        or to_float(row.get("last"))
        or to_float(row.get("mid"))
        or to_float(row.get("prevClose"))
    )
    prev = to_float(row.get("prevClose"))
    change_pct = ((price / prev - 1.0) * 100.0) if price and prev else None
    if price is None:
        return None
    return QuoteSignal(
        price=round(price, 4),
        change_pct=round(change_pct, 3) if change_pct is not None else None,
        source="tiingo_iex",
    )
