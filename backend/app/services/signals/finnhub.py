"""Finnhub: analyst recommendation trends, earnings calendar, real-time quote.

Free tier: 60 calls/min. The analyst-consensus trend is the standout signal —
it is not derivable from price and captures Wall Street positioning.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.config import get_settings
from app.services.signals.base import get_json, to_float
from app.services.signals.types import AnalystRatings, QuoteSignal

BASE = "https://finnhub.io/api/v1"


def _consensus(sb: int, b: int, h: int, s: int, ss: int) -> tuple[str, float]:
    total = sb + b + h + s + ss
    if total == 0:
        return "n/a", 0.0
    # Weighted score in [-1, +1]: strong buy = +2 ... strong sell = -2.
    score = (2 * sb + b - s - 2 * ss) / (2 * total)
    if score >= 0.5:
        label = "Strong Buy"
    elif score >= 0.15:
        label = "Buy"
    elif score > -0.15:
        label = "Hold"
    elif score > -0.5:
        label = "Sell"
    else:
        label = "Strong Sell"
    return label, round(score, 3)


async def fetch_analyst_ratings(ticker: str) -> AnalystRatings | None:
    key = get_settings().finnhub_api_key.strip()
    if not key:
        return None
    data = await get_json(f"{BASE}/stock/recommendation", params={"symbol": ticker, "token": key})
    if not isinstance(data, list) or not data:
        return None
    latest = data[0]  # Finnhub returns most-recent period first.
    sb = int(latest.get("strongBuy", 0) or 0)
    b = int(latest.get("buy", 0) or 0)
    h = int(latest.get("hold", 0) or 0)
    s = int(latest.get("sell", 0) or 0)
    ss = int(latest.get("strongSell", 0) or 0)
    label, score = _consensus(sb, b, h, s, ss)
    return AnalystRatings(
        strong_buy=sb, buy=b, hold=h, sell=s, strong_sell=ss,
        period=str(latest.get("period") or ""),
        consensus=label, score=score,
    )


async def fetch_earnings_days(ticker: str) -> int | None:
    key = get_settings().finnhub_api_key.strip()
    if not key:
        return None
    today = datetime.now(UTC).date()
    frm = today.isoformat()
    to = (today + timedelta(days=370)).isoformat()
    data = await get_json(
        f"{BASE}/calendar/earnings",
        params={"symbol": ticker, "from": frm, "to": to, "token": key},
    )
    if not isinstance(data, dict):
        return None
    rows = data.get("earningsCalendar") or []
    upcoming: list[int] = []
    for row in rows:
        raw = row.get("date")
        try:
            d = date.fromisoformat(str(raw))
        except (TypeError, ValueError):
            continue
        delta = (d - today).days
        if delta >= 0:
            upcoming.append(delta)
    return min(upcoming) if upcoming else None


async def fetch_quote(ticker: str) -> QuoteSignal | None:
    key = get_settings().finnhub_api_key.strip()
    if not key:
        return None
    data = await get_json(f"{BASE}/quote", params={"symbol": ticker, "token": key})
    if not isinstance(data, dict) or not data.get("c"):
        return None
    return QuoteSignal(
        price=to_float(data.get("c")),
        change_pct=to_float(data.get("dp")),
        source="finnhub",
    )
