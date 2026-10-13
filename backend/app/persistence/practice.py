"""Saved rules and a cash-only simulation ledger, separate from AI verdicts."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.db import Base
from app.security import utc_now


class Strategy(Base):
    __tablename__ = "saved_strategies"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rules: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PracticeAccount(Base):
    __tablename__ = "practice_accounts"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    cash_cents: Mapped[int] = mapped_column(Integer, default=10_000_000)
    # Updating this row serializes ledger changes for each account on SQLite/Postgres.
    version: Mapped[int] = mapped_column(Integer, default=0)


class PracticeQuote(Base):
    __tablename__ = "practice_quotes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    context: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PracticeTrade(Base):
    __tablename__ = "practice_trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    quote_id: Mapped[str] = mapped_column(String(36), unique=True)
    ticker: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[int] = mapped_column(Integer)
    entry_cents: Mapped[int] = mapped_column(Integer)
    exit_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context: Mapped[dict] = mapped_column(JSON)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_as_of: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str] = mapped_column(String(4000), default="")
