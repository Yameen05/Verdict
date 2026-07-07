"""The scoreboard — Verdict grades its own homework.

Every persisted run stores the price at verdict time. This endpoint replays
the book: forward return since each verdict, whether the call was right under
a disclosed rule, and the aggregate hit rate.

Scoring rule (deliberately simple, shown in the UI):
  Buy  is a hit if the price is up since the verdict,
  Sell is a hit if it is down,
  Hold is a hit if it stayed within ±5%.
Pending runs and runs without a captured price are listed but not scored.
"""

# NOTE: no `from __future__ import annotations` — see routers/research.py.

import asyncio
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.logging import get_logger
from app.persistence.db import list_recent_runs, session_scope
from app.services.cache import TTLCache
from app.services.metrics_client import MetricsClientError, fetch_price

router = APIRouter()
log = get_logger(__name__)

HOLD_BAND_PCT = 5.0
MAX_TICKERS_PRICED = 25

_price_cache: TTLCache[float | None] = TTLCache(600)  # 10 minutes


async def _cached_price(ticker: str) -> float | None:
    async def factory() -> float | None:
        try:
            return await asyncio.to_thread(fetch_price, ticker)
        except MetricsClientError as e:
            log.warning("scoreboard_price_failed", extra={"ticker": ticker, "reason": str(e)})
            return None

    return await _price_cache.get_or_set(ticker.upper(), factory)


def _reset_price_cache() -> None:
    _price_cache.clear()


class ScoreboardEntry(BaseModel):
    id: int
    ticker: str
    recommendation: str
    confidence: int | None = None
    created_at: datetime
    price_at_run: float | None = None
    current_price: float | None = None
    return_pct: float | None = None
    outcome: Literal["hit", "miss", "unscored"] = "unscored"


class ScoreboardSummary(BaseModel):
    total_runs: int = 0
    scored: int = 0
    hits: int = 0
    hit_rate: float | None = None  # 0-1
    avg_return_buy_pct: float | None = None
    rule: str = (
        f"Buy hits if price rose since the verdict; Sell hits if it fell; "
        f"Hold hits within ±{HOLD_BAND_PCT:.0f}%. Pending and price-less runs unscored."
    )


class ScoreboardResponse(BaseModel):
    entries: list[ScoreboardEntry] = Field(default_factory=list)
    summary: ScoreboardSummary


def _outcome(recommendation: str, return_pct: float) -> Literal["hit", "miss"]:
    if recommendation == "Buy":
        return "hit" if return_pct > 0 else "miss"
    if recommendation == "Sell":
        return "hit" if return_pct < 0 else "miss"
    return "hit" if abs(return_pct) <= HOLD_BAND_PCT else "miss"


@router.get("/scoreboard", response_model=ScoreboardResponse)
async def scoreboard(
    request: Request,
    limit: int = 100,
    session: AsyncSession = Depends(session_scope),
) -> ScoreboardResponse:
    rows = await list_recent_runs(
        session, limit=min(max(limit, 1), 500), user_id=request.state.user_id
    )

    # Price the distinct tickers concurrently (capped — yfinance is slow).
    scorable = [r for r in rows if r.price_at_run and r.recommendation != "Pending"]
    tickers = list(dict.fromkeys(r.ticker for r in scorable))[:MAX_TICKERS_PRICED]
    prices = dict(
        zip(
            tickers,
            await asyncio.gather(*(_cached_price(t) for t in tickers)),
            strict=True,
        )
    )

    entries: list[ScoreboardEntry] = []
    hits = 0
    scored = 0
    buy_returns: list[float] = []
    for r in rows:
        current = prices.get(r.ticker)
        entry = ScoreboardEntry(
            id=r.id,
            ticker=r.ticker,
            recommendation=r.recommendation,
            confidence=r.confidence,
            created_at=r.created_at,
            price_at_run=r.price_at_run,
            current_price=current,
        )
        if r.price_at_run and current and r.recommendation != "Pending":
            ret = (current - r.price_at_run) / r.price_at_run * 100.0
            entry.return_pct = round(ret, 2)
            entry.outcome = _outcome(r.recommendation, ret)
            scored += 1
            hits += entry.outcome == "hit"
            if r.recommendation == "Buy":
                buy_returns.append(ret)
        entries.append(entry)

    summary = ScoreboardSummary(
        total_runs=len(rows),
        scored=scored,
        hits=hits,
        hit_rate=round(hits / scored, 4) if scored else None,
        avg_return_buy_pct=(
            round(sum(buy_returns) / len(buy_returns), 2) if buy_returns else None
        ),
    )
    return ScoreboardResponse(entries=entries, summary=summary)
