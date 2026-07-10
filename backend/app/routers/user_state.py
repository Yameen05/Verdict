"""Per-user workspace state endpoints (watchlist, positions, alerts, levels).

Everything here is scoped to the authenticated user; no cross-user reads.
Tickers are validated with the same rule as the market router.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence import user_state as store
from app.persistence.db import session_scope
from app.security import AuthContext, require_authenticated

router = APIRouter()

MAX_WATCHLIST = 24
MAX_ALERTS = 50
MAX_LEVELS_PER_TICKER = 20


def _validate_ticker(raw: str) -> str:
    ticker = (raw or "").strip().upper()
    if not ticker or len(ticker) > 12 or not ticker.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid ticker")
    return ticker


# ----- Watchlist -----


class WatchlistBody(BaseModel):
    ticker: str


@router.get("/watchlist")
async def get_watchlist(
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    return {"tickers": await store.list_watchlist(session, auth.user.id)}


@router.post("/watchlist")
async def add_to_watchlist(
    body: WatchlistBody,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    ticker = _validate_ticker(body.ticker)
    current = await store.list_watchlist(session, auth.user.id)
    if ticker not in current and len(current) >= MAX_WATCHLIST:
        raise HTTPException(status_code=400, detail=f"Watchlist is capped at {MAX_WATCHLIST}")
    await store.add_watchlist(session, auth.user.id, ticker)
    return {"tickers": await store.list_watchlist(session, auth.user.id)}


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    await store.remove_watchlist(session, auth.user.id, _validate_ticker(ticker))
    return {"tickers": await store.list_watchlist(session, auth.user.id)}


# ----- Position tracker -----


class PositionBody(BaseModel):
    ticker: str
    amount_usd: float = Field(gt=0, le=100_000_000)
    buy_date: str
    buy_price: float | None = Field(default=None, gt=0)


class PositionResponse(BaseModel):
    ticker: str
    amount_usd: float
    buy_date: str
    buy_price: float | None


def _validate_buy_date(raw: str) -> str:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError as e:
        raise HTTPException(status_code=422, detail="buy_date must be YYYY-MM-DD") from e


@router.get("/positions/{ticker}")
async def get_position(
    ticker: str,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    row = await store.get_position(session, auth.user.id, _validate_ticker(ticker))
    if row is None:
        return {"position": None}
    return {
        "position": PositionResponse(
            ticker=row.ticker,
            amount_usd=row.amount_usd,
            buy_date=row.buy_date,
            buy_price=row.buy_price,
        )
    }


@router.post("/positions")
async def save_position(
    body: PositionBody,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    row = await store.upsert_position(
        session,
        auth.user.id,
        ticker=_validate_ticker(body.ticker),
        amount_usd=body.amount_usd,
        buy_date=_validate_buy_date(body.buy_date),
        buy_price=body.buy_price,
    )
    return {
        "position": PositionResponse(
            ticker=row.ticker,
            amount_usd=row.amount_usd,
            buy_date=row.buy_date,
            buy_price=row.buy_price,
        )
    }


@router.delete("/positions/{ticker}")
async def remove_position(
    ticker: str,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    await store.delete_position(session, auth.user.id, _validate_ticker(ticker))
    return {"position": None}


# ----- Price alerts -----


class AlertBody(BaseModel):
    ticker: str
    direction: Literal["above", "below"]
    price: float = Field(gt=0, le=100_000_000)


class AlertResponse(BaseModel):
    id: int
    ticker: str
    direction: str
    price: float
    triggered: bool
    triggered_at: str | None
    triggered_price: float | None
    created_at: str


def _iso_utc(dt: datetime) -> str:
    """SQLite returns naive datetimes on re-read; normalize both shapes to Z."""
    aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def _alert_response(row: store.PriceAlert) -> AlertResponse:
    return AlertResponse(
        id=row.id,
        ticker=row.ticker,
        direction=row.direction,
        price=row.price,
        triggered=row.triggered,
        triggered_at=_iso_utc(row.triggered_at) if row.triggered_at else None,
        triggered_price=row.triggered_price,
        created_at=_iso_utc(row.created_at),
    )


@router.get("/alerts")
async def get_alerts(
    ticker: str | None = None,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    validated = _validate_ticker(ticker) if ticker else None
    rows = await store.list_alerts(session, auth.user.id, validated)
    return {"alerts": [_alert_response(r) for r in rows]}


@router.post("/alerts")
async def create_alert(
    body: AlertBody,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    existing = await store.list_alerts(session, auth.user.id)
    if len(existing) >= MAX_ALERTS:
        raise HTTPException(status_code=400, detail=f"Alerts are capped at {MAX_ALERTS}")
    row = await store.create_alert(
        session,
        auth.user.id,
        ticker=_validate_ticker(body.ticker),
        direction=body.direction,
        price=round(body.price, 4),
    )
    return {"alert": _alert_response(row)}


@router.post("/alerts/{alert_id}/trigger")
async def trigger_alert(
    alert_id: int,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    """Client observed the crossing on its live chart before the worker did."""
    row = await store.get_alert(session, auth.user.id, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if not row.triggered:
        await store.mark_alert_triggered(session, row, row.price)
    return {"alert": _alert_response(row)}


@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: int,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    await store.delete_alert(session, auth.user.id, alert_id)
    return {"ok": True}


# ----- Chart price levels -----


class LevelBody(BaseModel):
    ticker: str
    price: float = Field(gt=0, le=100_000_000)


@router.get("/levels/{ticker}")
async def get_levels(
    ticker: str,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    return {"prices": await store.list_levels(session, auth.user.id, _validate_ticker(ticker))}


@router.post("/levels")
async def add_level(
    body: LevelBody,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    ticker = _validate_ticker(body.ticker)
    current = await store.list_levels(session, auth.user.id, ticker)
    price = round(body.price, 2)
    if price not in current and len(current) >= MAX_LEVELS_PER_TICKER:
        raise HTTPException(
            status_code=400, detail=f"Levels are capped at {MAX_LEVELS_PER_TICKER} per ticker"
        )
    await store.add_level(session, auth.user.id, ticker, price)
    return {"prices": await store.list_levels(session, auth.user.id, ticker)}


@router.delete("/levels/{ticker}")
async def clear_levels(
    ticker: str,
    price: float | None = None,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    validated = _validate_ticker(ticker)
    await store.clear_levels(session, auth.user.id, validated, price)
    return {"prices": await store.list_levels(session, auth.user.id, validated)}


# ----- Verdict watch -----


class VerdictWatchBody(BaseModel):
    ticker: str
    recommendation: str = Field(max_length=16)


@router.get("/verdict-watch/{ticker}")
async def get_verdict_watch(
    ticker: str,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    row = await store.get_verdict_watch(session, auth.user.id, _validate_ticker(ticker))
    return {"recommendation": row.recommendation if row else None}


@router.post("/verdict-watch")
async def set_verdict_watch(
    body: VerdictWatchBody,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    row = await store.set_verdict_watch(
        session, auth.user.id, _validate_ticker(body.ticker), body.recommendation.strip()
    )
    return {"recommendation": row.recommendation}


@router.delete("/verdict-watch/{ticker}")
async def clear_verdict_watch(
    ticker: str,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
) -> dict:
    await store.clear_verdict_watch(session, auth.user.id, _validate_ticker(ticker))
    return {"recommendation": None}
