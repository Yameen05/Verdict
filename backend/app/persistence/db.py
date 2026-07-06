"""Async SQLAlchemy engine + session for research history.

SQLite by default (single-file, no external service). Switch to Postgres by
overriding DATABASE_URL with a `postgresql+asyncpg://...` URI.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
    inspect,
    select,
    text,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class User(Base):
    """The self-hosted owner account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Enforce the single-owner deployment model at the database layer so two
    # simultaneous bootstrap requests cannot create two owners.
    singleton_key: Mapped[int] = mapped_column(Integer, default=1, unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_counter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recovery_code_hashes: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UserSession(Base):
    """Server-side session. Only a SHA-256 token digest is persisted."""

    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64))
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)


class LoginChallenge(Base):
    """Short-lived second-factor challenge created after password verification."""

    __tablename__ = "login_challenges"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AuditEvent(Base):
    """Security event log. Credentials, session tokens, and OTPs are never stored."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class ResearchRun(Base):
    """One row per completed /research call."""

    __tablename__ = "research_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ticker: Mapped[str] = mapped_column(String(10), index=True)
    recommendation: Mapped[str] = mapped_column(String(16))
    justification: Mapped[str] = mapped_column(Text)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)  # full ResearchResponse as JSON
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite URIs point at a file path; create parent dirs so engine creation works."""
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return
    raw = url[len(prefix) :]
    if raw == ":memory:" or raw.startswith(":"):
        return
    path = Path(raw).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)


def get_engine():
    global _engine, _sessionmaker
    if _engine is None:
        url = get_settings().database_url
        _ensure_sqlite_dir(url)
        engine_options = {"echo": False, "future": True}
        if url.startswith("sqlite+aiosqlite:"):
            engine_options["connect_args"] = {"timeout": 30}
        _engine = create_async_engine(url, **engine_options)
        if url.startswith("sqlite+aiosqlite:"):
            @event.listens_for(_engine.sync_engine, "connect")
            def _configure_sqlite(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # The project predates user accounts. create_all() does not add columns
        # to an existing table, so migrate the one legacy table in-place.
        await conn.run_sync(_migrate_legacy_schema)


def _migrate_legacy_schema(connection) -> None:
    tables = set(inspect(connection).get_table_names())
    if "users" in tables:
        user_columns = {c["name"] for c in inspect(connection).get_columns("users")}
        if "singleton_key" not in user_columns:
            connection.execute(
                text(
                    "ALTER TABLE users ADD COLUMN singleton_key "
                    "INTEGER NOT NULL DEFAULT 1"
                )
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_singleton_key "
                "ON users (singleton_key)"
            )
        )
        if "totp_last_counter" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN totp_last_counter INTEGER")
            )
    if "research_runs" not in tables:
        return
    columns = {c["name"] for c in inspect(connection).get_columns("research_runs")}
    if "user_id" not in columns:
        connection.execute(
            text(
                "ALTER TABLE research_runs ADD COLUMN user_id INTEGER "
                "REFERENCES users(id) ON DELETE CASCADE"
            )
        )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_research_runs_user_id "
            "ON research_runs (user_id)"
        )
    )


async def session_scope() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: async session yielded as a context manager."""
    get_engine()
    if _sessionmaker is None:
        raise RuntimeError("Database session factory was not initialized")
    async with _sessionmaker() as session:
        yield session


async def save_run(
    session: AsyncSession,
    *,
    ticker: str,
    recommendation: str,
    justification: str,
    sentiment_score: float | None,
    payload: dict,
    duration_ms: float | None = None,
    cost_usd: float | None = None,
    request_id: str | None = None,
    user_id: int | None = None,
) -> ResearchRun:
    row = ResearchRun(
        user_id=user_id,
        ticker=ticker.upper(),
        recommendation=recommendation,
        justification=justification,
        sentiment_score=sentiment_score,
        payload=payload,
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        request_id=request_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_runs_for_ticker(
    session: AsyncSession,
    ticker: str,
    limit: int = 20,
    user_id: int | None = None,
) -> list[ResearchRun]:
    stmt = select(ResearchRun).where(ResearchRun.ticker == ticker.upper())
    if user_id is not None:
        stmt = stmt.where(ResearchRun.user_id == user_id)
    stmt = stmt.order_by(ResearchRun.created_at.desc()).limit(limit)
    res = await session.execute(stmt)
    return list(res.scalars().all())


# Test helper — wiped between tests via dependency override or env var.
def _reset_for_tests() -> None:
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
    if os.environ.get("DATABASE_URL", "").endswith(":memory:"):
        return
