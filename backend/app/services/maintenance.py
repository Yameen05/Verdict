"""Housekeeping for expired authentication credentials and price previews.

Research history, users, trades, invites and audit records are preserved.
"""

import asyncio

from sqlalchemy import delete

from app.observability.logging import get_logger
from app.persistence.db import get_sessionmaker
from app.persistence.practice import PracticeQuote
from app.security import purge_expired_auth_rows, utc_now


async def clean_expired() -> None:
    async with get_sessionmaker()() as db:
        await purge_expired_auth_rows(db)
        await db.execute(delete(PracticeQuote).where(PracticeQuote.expires_at <= utc_now()))
        await db.commit()


async def run_worker(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await clean_expired()
        except Exception:
            get_logger(__name__).exception("expiry_cleanup_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=3600)
        except TimeoutError:
            pass
