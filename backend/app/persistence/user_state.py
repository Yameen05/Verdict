"""Per-user workspace state: positions, price alerts, chart levels, watchlist.

These lived in browser localStorage before, which meant an invited user lost
everything when they switched machines and alerts could only fire while a tab
was open. Each table is tiny and keyed by user; routers/user_state.py exposes
the CRUD and services/alerts_worker.py evaluates alerts server-side.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.db import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="ux_watchlist_user_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Position(Base):
    """One tracked position per (user, ticker) — mirrors the Position tracker form."""

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="ux_positions_user_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(12))
    amount_usd: Mapped[float] = mapped_column(Float)
    buy_date: Mapped[str] = mapped_column(String(10))  # ISO date, e.g. 2026-07-01
    buy_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(12), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # "above" | "below"
    price: Mapped[float] = mapped_column(Float)
    triggered: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    triggered_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ChartLevel(Base):
    """A horizontal price line the user drew on the chart."""

    __tablename__ = "chart_levels"
    __table_args__ = (
        UniqueConstraint("user_id", "ticker", "price", name="ux_levels_user_ticker_price"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(12))
    price: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class VerdictWatch(Base):
    """User armed 'tell me when the verdict changes from X' for a ticker."""

    __tablename__ = "verdict_watches"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="ux_vwatch_user_ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    ticker: Mapped[str] = mapped_column(String(12))
    recommendation: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


# ----- CRUD helpers (all scoped to a user id) -----


async def list_watchlist(session: AsyncSession, user_id: int) -> list[str]:
    rows = await session.scalars(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user_id)
        .order_by(WatchlistItem.created_at)
    )
    return [row.ticker for row in rows]


async def add_watchlist(session: AsyncSession, user_id: int, ticker: str) -> None:
    existing = await session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user_id, WatchlistItem.ticker == ticker
        )
    )
    if existing is None:
        session.add(WatchlistItem(user_id=user_id, ticker=ticker))
        await session.commit()


async def remove_watchlist(session: AsyncSession, user_id: int, ticker: str) -> None:
    row = await session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user_id, WatchlistItem.ticker == ticker
        )
    )
    if row is not None:
        await session.delete(row)
        await session.commit()


async def get_position(
    session: AsyncSession, user_id: int, ticker: str
) -> Position | None:
    return await session.scalar(
        select(Position).where(Position.user_id == user_id, Position.ticker == ticker)
    )


async def upsert_position(
    session: AsyncSession,
    user_id: int,
    *,
    ticker: str,
    amount_usd: float,
    buy_date: str,
    buy_price: float | None,
) -> Position:
    row = await get_position(session, user_id, ticker)
    if row is None:
        row = Position(user_id=user_id, ticker=ticker)
        session.add(row)
    row.amount_usd = amount_usd
    row.buy_date = buy_date
    row.buy_price = buy_price
    await session.commit()
    await session.refresh(row)
    return row


async def delete_position(session: AsyncSession, user_id: int, ticker: str) -> None:
    row = await get_position(session, user_id, ticker)
    if row is not None:
        await session.delete(row)
        await session.commit()


async def list_alerts(
    session: AsyncSession, user_id: int, ticker: str | None = None
) -> list[PriceAlert]:
    stmt = select(PriceAlert).where(PriceAlert.user_id == user_id)
    if ticker is not None:
        stmt = stmt.where(PriceAlert.ticker == ticker)
    rows = await session.scalars(stmt.order_by(PriceAlert.created_at))
    return list(rows)


async def create_alert(
    session: AsyncSession,
    user_id: int,
    *,
    ticker: str,
    direction: str,
    price: float,
) -> PriceAlert:
    row = PriceAlert(user_id=user_id, ticker=ticker, direction=direction, price=price)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_alert(session: AsyncSession, user_id: int, alert_id: int) -> PriceAlert | None:
    return await session.scalar(
        select(PriceAlert).where(PriceAlert.id == alert_id, PriceAlert.user_id == user_id)
    )


async def delete_alert(session: AsyncSession, user_id: int, alert_id: int) -> None:
    row = await get_alert(session, user_id, alert_id)
    if row is not None:
        await session.delete(row)
        await session.commit()


async def mark_alert_triggered(
    session: AsyncSession, alert: PriceAlert, price: float
) -> None:
    alert.triggered = True
    alert.triggered_at = datetime.now(UTC)
    alert.triggered_price = price
    await session.commit()


async def list_pending_alerts(session: AsyncSession) -> list[PriceAlert]:
    """All untriggered alerts across users — the background worker's work queue."""
    rows = await session.scalars(
        select(PriceAlert).where(PriceAlert.triggered.is_(False))
    )
    return list(rows)


async def list_levels(session: AsyncSession, user_id: int, ticker: str) -> list[float]:
    rows = await session.scalars(
        select(ChartLevel)
        .where(ChartLevel.user_id == user_id, ChartLevel.ticker == ticker)
        .order_by(ChartLevel.price)
    )
    return [row.price for row in rows]


async def add_level(
    session: AsyncSession, user_id: int, ticker: str, price: float
) -> None:
    existing = await session.scalar(
        select(ChartLevel).where(
            ChartLevel.user_id == user_id,
            ChartLevel.ticker == ticker,
            ChartLevel.price == price,
        )
    )
    if existing is None:
        session.add(ChartLevel(user_id=user_id, ticker=ticker, price=price))
        await session.commit()


async def clear_levels(
    session: AsyncSession, user_id: int, ticker: str, price: float | None = None
) -> None:
    stmt = select(ChartLevel).where(
        ChartLevel.user_id == user_id, ChartLevel.ticker == ticker
    )
    if price is not None:
        stmt = stmt.where(ChartLevel.price == price)
    rows = await session.scalars(stmt)
    deleted = False
    for row in rows:
        await session.delete(row)
        deleted = True
    if deleted:
        await session.commit()


async def get_verdict_watch(
    session: AsyncSession, user_id: int, ticker: str
) -> VerdictWatch | None:
    return await session.scalar(
        select(VerdictWatch).where(
            VerdictWatch.user_id == user_id, VerdictWatch.ticker == ticker
        )
    )


async def set_verdict_watch(
    session: AsyncSession, user_id: int, ticker: str, recommendation: str
) -> VerdictWatch:
    row = await get_verdict_watch(session, user_id, ticker)
    if row is None:
        row = VerdictWatch(user_id=user_id, ticker=ticker)
        session.add(row)
    row.recommendation = recommendation
    await session.commit()
    await session.refresh(row)
    return row


async def clear_verdict_watch(session: AsyncSession, user_id: int, ticker: str) -> None:
    row = await get_verdict_watch(session, user_id, ticker)
    if row is not None:
        await session.delete(row)
        await session.commit()
