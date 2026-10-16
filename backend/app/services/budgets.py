"""Persistent atomic admission counters: reserve BEFORE spending provider quota.

Failed and cancelled attempts remain charged because providers may bill them.
Caches bypass admission; no tokens or plaintext email addresses are persisted.
"""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import DateTime, Integer, String, delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.persistence.db import Base, count_runs_since, get_sessionmaker
from app.schemas.failure import FailureInfo


class AdmissionCounter(Base):
    __tablename__ = "admission_counters"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


async def _claim(db, key: str, limit: int, expires_at: datetime, initial: int = 0) -> bool:
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    await db.execute(insert(AdmissionCounter).values(
        key=key, used=initial, expires_at=expires_at,
    ).on_conflict_do_nothing(index_elements=["key"]))
    changed = await db.execute(update(AdmissionCounter).where(
        AdmissionCounter.key == key, AdmissionCounter.used < limit,
    ).values(used=AdmissionCounter.used + 1))
    return changed.rowcount == 1


async def reserve_provider_operation(user_id: int | None) -> None:
    settings = get_settings()
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    async with get_sessionmaker()() as db:
        # The insert/update on the global row serializes concurrent admissions.
        # Existing research history seeds the first counter after an upgrade.
        global_used = await count_runs_since(db, start)
        allowed = await _claim(db, f"provider:{start.date()}:global",
                               settings.daily_runs_global, end, global_used)
        personal = True
        if allowed and user_id is not None:
            user_used = await count_runs_since(db, start, user_id=user_id)
            personal = await _claim(db, f"provider:{start.date()}:user:{user_id}",
                                    settings.daily_runs_per_user, end, user_used)
        if not allowed or not personal:
            await db.rollback()
            prefix = "Verdict's community limit" if not allowed else "You've used your daily limit"
            raise HTTPException(429, detail=FailureInfo(
                kind="app_daily_limit", window="day", reset_at=end.isoformat(),
                message=f"{prefix} for fresh runs and paid operations was reached. Cached reports remain available; resets at midnight UTC.",
            ).model_dump())
        await db.execute(delete(AdmissionCounter).where(AdmissionCounter.expires_at <= start))
        await db.commit()


async def reserve_auth_attempt(email: str, action: str, limit: int, seconds: int) -> None:
    now = datetime.now(UTC)
    slot = int(now.timestamp()) // seconds
    digest = sha256(email.encode()).hexdigest()
    end = datetime.fromtimestamp((slot + 1) * seconds, UTC)
    async with get_sessionmaker()() as db:
        if not await _claim(db, f"{action}:{slot}:{digest}", limit, end):
            await db.rollback()
            raise HTTPException(429, "Too many attempts. Please try again later")
        await db.execute(delete(AdmissionCounter).where(AdmissionCounter.expires_at <= now))
        await db.commit()
