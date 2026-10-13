"""Fetch horizon prices and freeze finished verdict grades."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.observability.logging import get_logger
from app.persistence.db import ResearchRun, get_sessionmaker
from app.services.assessment import has_issued_prediction
from app.services.backtest import BacktestEntry, due_at, evaluate_run
from app.services.cache import TTLCache
from app.services.metrics_client import MetricsClientError, PriceBar, fetch_price_history

log = get_logger(__name__)
_history_cache: TTLCache[list[PriceBar]] = TTLCache(60, maxsize=256)
MAX_TICKERS = 25


async def daily_history(ticker: str) -> list[PriceBar]:
    async def factory():
        try:
            bars, _ = await asyncio.to_thread(fetch_price_history, ticker, "5Y", "1D")
            return bars
        except MetricsClientError as exc:
            log.warning("track_record_price_failed", extra={"ticker": ticker, "reason": str(exc)})
            return []

    return await _history_cache.get_or_set(ticker.upper(), factory)


async def grade_runs(
    session: AsyncSession, rows: list[ResearchRun], *, now: datetime | None = None
) -> list[BacktestEntry]:
    now = now or datetime.now(UTC)
    due = [
        r
        for r in rows
        if not r.horizon_evaluation
        and due_at(r) is not None
        and due_at(r) <= now
        and r.price_at_run
        and r.price_at_run > 0
        and r.recommendation in {"Buy", "Sell", "Hold"}
        and has_issued_prediction(r)
    ]
    tickers = list(dict.fromkeys(r.ticker.upper() for r in due))[:MAX_TICKERS]
    fetched = await asyncio.gather(*(daily_history(t) for t in tickers))
    histories = dict(zip(tickers, fetched, strict=True))
    entries = []
    for row in rows:
        entry = evaluate_run(row, histories.get(row.ticker.upper(), []), now=now)
        if entry.outcome in {"hit", "miss"} and not row.horizon_evaluation:
            snapshot = entry.model_dump(mode="json")
            # A request and the worker can finish together; the first final
            # snapshot wins, including across multiple server processes.
            await session.execute(
                update(ResearchRun)
                .where(ResearchRun.id == row.id, ResearchRun.horizon_evaluation.is_(None))
                .values(horizon_evaluation=snapshot)
                .execution_options(synchronize_session=False)
            )
            await session.commit()
            await session.refresh(row)
            entry = evaluate_run(row, [], now=now)
        entries.append(entry)
    return entries


async def evaluate_due_once(session: AsyncSession) -> int:
    rows = list(
        await session.scalars(
            select(ResearchRun)
            .where(
                ResearchRun.horizon_evaluation.is_(None),
                ResearchRun.price_at_run > 0,
                ResearchRun.recommendation.in_(["Buy", "Sell", "Hold"]),
            )
            .order_by(ResearchRun.created_at)
        )
    )
    now = datetime.now(UTC)
    due = [
        r for r in rows if due_at(r) is not None and due_at(r) <= now and has_issued_prediction(r)
    ]
    # Work through every due ticker so an outage in the first batch cannot
    # indefinitely starve later calls of evaluation.
    tickers = list(dict.fromkeys(r.ticker.upper() for r in due))
    finished = 0
    for start in range(0, len(tickers), MAX_TICKERS):
        batch = set(tickers[start : start + MAX_TICKERS])
        entries = await grade_runs(session, [r for r in due if r.ticker.upper() in batch], now=now)
        finished += sum(e.outcome in {"hit", "miss"} for e in entries)
    return finished


async def run_worker(stop: asyncio.Event, interval: int = 60) -> None:
    while not stop.is_set():
        try:
            async with get_sessionmaker()() as session:
                await evaluate_due_once(session)
        except Exception:  # noqa: BLE001 - a provider outage must not stop future grading
            log.exception("track_record_evaluation_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
