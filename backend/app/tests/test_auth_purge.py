"""Expired auth rows are removed rather than accumulating forever."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app.persistence.db import (
    LoginChallenge,
    PasswordResetToken,
    User,
    UserSession,
    get_sessionmaker,
    init_db,
)
from app.security import hash_password, new_token, purge_expired_auth_rows, token_digest, utc_now


async def _count(session, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_purge_removes_only_expired_rows():
    await init_db()
    now = utc_now()
    async with get_sessionmaker()() as session:
        user = User(
            email="owner@example.com",
            password_hash=hash_password("a-strong-test-password-123"),
            role="owner",
        )
        session.add(user)
        await session.flush()

        for offset, tag in ((timedelta(hours=-1), "stale"), (timedelta(hours=1), "live")):
            session.add(
                UserSession(
                    token_hash=token_digest(f"session-{tag}"),
                    user_id=user.id,
                    csrf_token=new_token(24),
                    mfa_verified=True,
                    expires_at=now + offset,
                    last_seen_at=now,
                )
            )
            session.add(
                LoginChallenge(
                    token_hash=token_digest(f"challenge-{tag}"),
                    user_id=user.id,
                    expires_at=now + offset,
                )
            )
            session.add(
                PasswordResetToken(
                    token_hash=token_digest(f"reset-{tag}"),
                    user_id=user.id,
                    expires_at=now + offset,
                )
            )
        await session.commit()

        assert await _count(session, UserSession) == 2

        removed = await purge_expired_auth_rows(session)
        assert removed == 3

        assert await _count(session, UserSession) == 1
        assert await _count(session, LoginChallenge) == 1
        assert await _count(session, PasswordResetToken) == 1
        # The surviving rows are the unexpired ones.
        survivor = await session.scalar(select(UserSession))
        assert survivor.token_hash == token_digest("session-live")


async def test_purge_is_a_no_op_on_an_empty_database():
    await init_db()
    async with get_sessionmaker()() as session:
        assert await purge_expired_auth_rows(session) == 0
