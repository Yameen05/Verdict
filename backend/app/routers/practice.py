"""User-owned strategies and an atomic, cash-only pretend-money ledger."""

import asyncio
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.limiter import limiter
from app.persistence.db import session_scope
from app.persistence.practice import PracticeAccount, PracticeQuote, PracticeTrade, Strategy
from app.persistence.user_state import list_watchlist
from app.routers.user_state import _iso_utc, lock_user_state
from app.schemas.practice import NotesBody, PlaceBody, QuoteBody, Rules, ScanBody
from app.security import AuthContext, require_authenticated, utc_now
from app.services import strategies as engine
from app.services.stock_directory import get_stock_directory

router = APIRouter()


def cents(value: float) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


async def owned(session, model, user_id, row_id):
    row = await session.scalar(select(model).where(model.user_id == user_id, model.id == row_id))
    if row is None:
        raise HTTPException(404, "That saved search or practice trade is not available")
    return row


async def ensure_account(session, user_id):
    # Savepoint keeps a simultaneous first visit from creating two accounts.
    if await session.get(PracticeAccount, user_id) is None:
        try:
            async with session.begin_nested():
                session.add(PracticeAccount(user_id=user_id))
                await session.flush()
        except IntegrityError:
            pass
        await session.commit()


async def lock_account(session, user_id):
    await ensure_account(session, user_id)
    await session.execute(
        update(PracticeAccount)
        .where(PracticeAccount.user_id == user_id)
        .values(version=PracticeAccount.version + 1)
    )


async def allowed_tickers(session, user_id, universe):
    if universe == "liquid":
        return list(engine.LIQUID_UNIVERSE), []
    tickers = (await list_watchlist(session, user_id))[:24]
    if not tickers:
        return [], []
    try:
        listed = {a.ticker for a in (await get_stock_directory()).assets}
    except Exception as exc:
        raise HTTPException(
            503,
            "We cannot check the names on your watchlist right now. Try the starter list or come back later",
        ) from exc
    included = [t for t in tickers if t in listed]
    return included, [
        {
            "ticker": t,
            "reason": "This is not a supported US stock or fund. Coins are not included here",
        }
        for t in tickers
        if t not in listed
    ]


@router.get("/strategies")
async def strategies(
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    rows = await session.scalars(
        select(Strategy).where(Strategy.user_id == auth.user.id).order_by(Strategy.id)
    )
    return {
        "strategies": [{"id": s.id, **s.rules} for s in rows],
        "templates": engine.TEMPLATES,
        "liquid_universe": engine.LIQUID_UNIVERSE,
        "data_note": engine.DATA_NOTE,
    }


@router.post("/strategies")
async def save_strategy(
    body: Rules,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    await lock_user_state(session, auth.user.id)
    count = await session.scalar(
        select(func.count()).select_from(Strategy).where(Strategy.user_id == auth.user.id)
    )
    if count >= 30:
        raise HTTPException(400, "You can keep 30 saved searches. Delete one before adding another")
    row = Strategy(user_id=auth.user.id, rules=body.model_dump())
    session.add(row)
    await session.commit()
    return {"id": row.id, **row.rules}


@router.post("/strategies/{strategy_id}")
async def edit_strategy(
    strategy_id: int,
    body: Rules,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    row = await owned(session, Strategy, auth.user.id, strategy_id)
    row.rules = body.model_dump()
    await session.commit()
    return {"id": row.id, **row.rules}


@router.delete("/strategies/{strategy_id}")
async def remove_strategy(
    strategy_id: int,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    row = await owned(session, Strategy, auth.user.id, strategy_id)
    await session.delete(row)
    await session.commit()
    return {"ok": True}


@router.post("/strategies/{strategy_id}/scan")
@limiter.limit("6/minute")
async def scan(
    request: Request,
    strategy_id: int,
    body: ScanBody,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    row = await owned(session, Strategy, auth.user.id, strategy_id)
    rules = Rules.model_validate(row.rules)
    tickers, skipped = await allowed_tickers(session, auth.user.id, body.universe)

    async def one(ticker):
        try:
            result = engine.evaluate(rules, await engine.market_bars(ticker))
            return {"ticker": ticker, **result}
        except engine.DataUnavailable as exc:
            return {"ticker": ticker, "reason": str(exc)}

    evaluated = await asyncio.gather(*(one(t) for t in tickers))
    results = [r for r in evaluated if "matched" in r]
    skipped.extend(r for r in evaluated if "reason" in r)
    return {
        "strategy": {"id": row.id, **row.rules},
        "universe": body.universe,
        "tickers": tickers,
        "scanned_at": _iso_utc(utc_now()),
        "results": sorted(
            results, key=lambda r: (-r["rules_passed"] / r["rules_total"], r["ticker"])
        ),
        "skipped": skipped,
        "data_note": engine.DATA_NOTE,
    }


@router.post("/practice/quote")
@limiter.limit("20/minute")
async def quote(
    request: Request,
    body: QuoteBody,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    strategy = await owned(session, Strategy, auth.user.id, body.strategy_id)
    if body.ticker not in engine.LIQUID_UNIVERSE:
        watchlist, _ = await allowed_tickers(session, auth.user.id, "watchlist")
        if body.ticker not in watchlist:
            raise HTTPException(
                400, "Choose a stock or fund from the starter list or your watchlist"
            )
    try:
        evaluation = engine.evaluate(
            Rules.model_validate(strategy.rules), await engine.market_bars(body.ticker)
        )
    except engine.DataUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    entry = cents(evaluation["close"])
    if entry < 1:
        raise HTTPException(
            422, "This price is less than one cent, so this practice account cannot use it"
        )
    context = {
        "ticker": body.ticker,
        "strategy": {"id": strategy.id, **strategy.rules},
        "evaluation": evaluation,
        "entry_price": entry / 100,
        "data_note": engine.DATA_NOTE,
    }
    now = utc_now()
    await session.execute(
        delete(PracticeQuote).where(
            PracticeQuote.user_id == auth.user.id, PracticeQuote.expires_at < now
        )
    )
    row = PracticeQuote(
        id=str(uuid4()),
        user_id=auth.user.id,
        context=context,
        expires_at=now + timedelta(minutes=2),
    )
    session.add(row)
    await session.commit()
    return {"id": row.id, "expires_at": _iso_utc(row.expires_at), **context}


def trade_json(row):
    pnl = (
        (row.exit_cents - row.entry_cents) * row.quantity / 100
        if row.exit_cents is not None
        else None
    )
    return {
        "id": row.id,
        "ticker": row.ticker,
        "quantity": row.quantity,
        "entry_price": row.entry_cents / 100,
        "exit_price": row.exit_cents / 100 if row.exit_cents is not None else None,
        "opened_at": _iso_utc(row.opened_at),
        "closed_at": _iso_utc(row.closed_at) if row.closed_at else None,
        "exit_as_of": row.exit_as_of,
        "realized_pnl": pnl,
        "context": row.context,
        "notes": row.notes,
    }


@router.get("/practice")
async def account(
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    await ensure_account(session, auth.user.id)
    # Read cash + trades in a single statement to keep the ledger snapshot coherent.
    rows = (
        await session.execute(
            select(PracticeAccount.cash_cents, PracticeTrade)
            .outerjoin(PracticeTrade, PracticeTrade.user_id == PracticeAccount.user_id)
            .where(PracticeAccount.user_id == auth.user.id)
            .order_by(PracticeTrade.id.desc())
        )
    ).all()
    cash = rows[0][0]
    trades = [r[1] for r in rows if r[1] is not None]

    async def mark(ticker):
        try:
            bar = (await engine.market_bars(ticker))[-1]
            if cents(bar.close) < 1:
                raise engine.DataUnavailable(
                    "This price is less than one cent, so we cannot use it"
                )
            return ticker, {"price": cents(bar.close) / 100, "as_of": bar.time}
        except engine.DataUnavailable as exc:
            return ticker, {"reason": str(exc)}

    marks = dict(
        await asyncio.gather(*(mark(t) for t in {r.ticker for r in trades if r.closed_at is None}))
    )
    open_trades = [r for r in trades if r.closed_at is None]
    complete = all(
        "price" in marks[r.ticker]
        and marks[r.ticker]["as_of"][:10] >= r.context["evaluation"]["as_of"][:10]
        for r in open_trades
    )
    market_value = (
        sum(cents(marks[r.ticker]["price"]) * r.quantity for r in open_trades) if complete else None
    )
    cost = sum(r.entry_cents * r.quantity for r in open_trades)
    realized = sum(
        (r.exit_cents - r.entry_cents) * r.quantity for r in trades if r.exit_cents is not None
    )
    return {
        "starting_cash": 100_000,
        "cash": cash / 100,
        "open_cost": cost / 100,
        "market_value": market_value / 100 if market_value is not None else None,
        "equity": (cash + market_value) / 100 if market_value is not None else None,
        "unrealized_pnl": (market_value - cost) / 100 if market_value is not None else None,
        "realized_pnl": realized / 100,
        "trades": [trade_json(r) for r in trades],
        "marks": marks,
        "data_note": engine.DATA_NOTE,
    }


@router.post("/practice/trades")
async def place(
    body: PlaceBody,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    await lock_account(session, auth.user.id)
    # The quote is a one-use idempotency key. Retries cannot spend cash twice.
    existing = await session.scalar(
        select(PracticeTrade).where(
            PracticeTrade.user_id == auth.user.id, PracticeTrade.quote_id == body.quote_id
        )
    )
    if existing:
        result = trade_json(existing)
        await session.rollback()
        return result
    row = await owned(session, PracticeQuote, auth.user.id, body.quote_id)
    if _iso_utc(row.expires_at) <= _iso_utc(utc_now()):
        raise HTTPException(
            409, "This price preview has expired. Update the price preview and try again"
        )
    entry = cents(row.context["entry_price"])
    stop, target = cents(body.stop), cents(body.target)
    if not 0 < stop < entry < target:
        raise HTTPException(
            422,
            "Your lower sell price must be below the buying price, and your higher sell price must be above it",
        )
    debit = entry * body.quantity
    changed = await session.execute(
        update(PracticeAccount)
        .where(PracticeAccount.user_id == auth.user.id, PracticeAccount.cash_cents >= debit)
        .values(cash_cents=PracticeAccount.cash_cents - debit)
    )
    if changed.rowcount != 1:
        raise HTTPException(
            409, "You do not have enough pretend money for that many shares. Try fewer shares"
        )
    trade = PracticeTrade(
        user_id=auth.user.id,
        quote_id=row.id,
        ticker=row.context["ticker"],
        quantity=body.quantity,
        entry_cents=entry,
        context={
            **row.context,
            "plan": {
                "stop": stop / 100,
                "target": target / 100,
                "thesis": body.thesis,
                "risk_usd": (entry - stop) * body.quantity / 100,
                "reward_usd": (target - entry) * body.quantity / 100,
            },
        },
    )
    session.add(trade)
    await session.commit()
    return trade_json(trade)


@router.post("/practice/trades/{trade_id}/close")
@limiter.limit("20/minute")
async def close(
    request: Request,
    trade_id: int,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    trade = await owned(session, PracticeTrade, auth.user.id, trade_id)
    if trade.closed_at:
        return trade_json(trade)
    try:
        bar = (await engine.market_bars(trade.ticker))[-1]
    except engine.DataUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    exit_price = cents(bar.close)
    if exit_price < 1 or bar.time[:10] < trade.context["evaluation"]["as_of"][:10]:
        raise HTTPException(
            409,
            "We need a valid price at least as recent as the one you bought at before you can sell",
        )
    await lock_account(session, auth.user.id)
    changed = await session.execute(
        update(PracticeTrade)
        .where(
            PracticeTrade.id == trade_id,
            PracticeTrade.user_id == auth.user.id,
            PracticeTrade.closed_at.is_(None),
        )
        .values(exit_cents=exit_price, exit_as_of=bar.time, closed_at=utc_now())
    )
    if changed.rowcount == 1:
        await session.execute(
            update(PracticeAccount)
            .where(PracticeAccount.user_id == auth.user.id)
            .values(cash_cents=PracticeAccount.cash_cents + exit_price * trade.quantity)
        )
    await session.commit()
    await session.refresh(trade)
    return trade_json(trade)


@router.post("/practice/trades/{trade_id}/notes")
async def notes(
    trade_id: int,
    body: NotesBody,
    auth: AuthContext = Depends(require_authenticated),
    session: AsyncSession = Depends(session_scope),
):
    # Field-specific UPDATE cannot overwrite concurrent close/accounting changes.
    trade = await owned(session, PracticeTrade, auth.user.id, trade_id)
    await session.execute(
        update(PracticeTrade)
        .where(PracticeTrade.id == trade.id, PracticeTrade.user_id == auth.user.id)
        .values(notes=body.notes)
    )
    await session.commit()
    await session.refresh(trade)
    return trade_json(trade)
