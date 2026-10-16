"""Authentication primitives and FastAPI dependencies.

The browser receives only a random, HttpOnly session token. The database stores
its SHA-256 digest, so a database read alone cannot be used to hijack a session.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.netaddr import client_ip
from app.observability.logging import get_request_id
from app.persistence.db import (
    AuditEvent,
    GoogleLoginNonce,
    LoginChallenge,
    PasswordResetToken,
    User,
    UserSession,
    session_scope,
)

PASSWORD_HASHER = PasswordHasher(
    time_cost=2,
    memory_cost=19_456,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)
_DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(
    "this-dummy-password-is-never-a-valid-account-password"
)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(slots=True)
class AuthContext:
    user: User
    session: UserSession


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if len(normalized) > 254 or not _EMAIL_RE.fullmatch(normalized):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    return normalized


def validate_password(password: str) -> None:
    if len(password) < 15:
        raise HTTPException(status_code=422, detail="Password must be at least 15 characters")
    if len(password) > 128:
        raise HTTPException(status_code=422, detail="Password must be at most 128 characters")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=422, detail="Password must contain a capital letter")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=422, detail="Password must contain a number")


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(stored_hash: str | None, candidate: str) -> bool:
    target = stored_hash or _DUMMY_PASSWORD_HASH
    try:
        matches = PASSWORD_HASHER.verify(target, candidate)
        # Google-only accounts have no password. The timing dummy must never
        # become a usable password for those accounts.
        return bool(stored_hash) and matches
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(stored_hash: str) -> bool:
    return PASSWORD_HASHER.check_needs_rehash(stored_hash)


def new_token(byte_length: int = 32) -> str:
    return secrets.token_urlsafe(byte_length)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_ip(request: Request) -> str:
    """Client address for audit records — proxy-aware, never a raw header."""
    return client_ip(request)[:64]


def request_user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:256]


async def record_audit(
    session: AsyncSession,
    request: Request,
    event: str,
    *,
    user_id: int | None = None,
    details: dict | None = None,
) -> None:
    session.add(
        AuditEvent(
            user_id=user_id,
            event=event[:64],
            request_id=get_request_id()[:64] or None,
            ip_address=request_ip(request) or None,
            user_agent=request_user_agent(request) or None,
            details=details or {},
        )
    )


async def create_session(
    db: AsyncSession,
    request: Request,
    user: User,
) -> tuple[UserSession, str]:
    settings = get_settings()
    raw_token = new_token()
    now = utc_now()
    row = UserSession(
        token_hash=token_digest(raw_token),
        user_id=user.id,
        csrf_token=new_token(24),
        mfa_verified=True,  # Legacy column retained for existing databases.
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        ip_address=request_ip(request) or None,
        user_agent=request_user_agent(request) or None,
    )
    db.add(row)
    return row, raw_token


def set_session_cookie(response: Response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'


async def get_auth_context(
    request: Request,
    db: Annotated[AsyncSession, Depends(session_scope)],
) -> AuthContext:
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Authentication required")

    result = await db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == token_digest(raw_token))
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=401, detail="Session is invalid or expired")
    user_session, user = row

    now = utc_now()
    idle_deadline = as_utc(user_session.last_seen_at) + timedelta(
        minutes=settings.session_idle_minutes
    )
    if (
        not user.is_active
        or as_utc(user_session.expires_at) <= now
        or idle_deadline <= now
    ):
        await db.execute(
            delete(UserSession).where(UserSession.token_hash == user_session.token_hash)
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Session is invalid or expired")

    if as_utc(user_session.last_seen_at) < now - timedelta(minutes=1):
        user_session.last_seen_at = now
        await db.commit()

    request.state.user_id = user.id
    return AuthContext(user=user, session=user_session)


def verify_csrf(request: Request, context: AuthContext) -> None:
    if request.method.upper() in _SAFE_METHODS:
        return
    provided = request.headers.get("x-csrf-token") or ""
    if not secrets.compare_digest(provided.encode("utf-8"), context.session.csrf_token.encode("utf-8")):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


async def require_authenticated(
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthContext:
    verify_csrf(request, context)
    from app.services.budgets import reserve_auth_attempt
    read = request.method.upper() in _SAFE_METHODS
    await reserve_auth_attempt(str(context.user.id), "api-read" if read else "api-write",
                               240 if read else 120, 60)
    return context


def basic_auth_payload(context: AuthContext) -> dict:
    return {
        "user": {
            "id": context.user.id,
            "email": context.user.email,
            "role": context.user.role,
        },
        "csrf_token": context.session.csrf_token,
    }


async def purge_expired_auth_rows(db: AsyncSession) -> int:
    """Delete auth rows that are past their expiry. Returns how many went.

    Expired rows are otherwise only removed when their own token is presented
    again, so abandoned sessions and unredeemed challenges accumulate forever.
    None of them can still authenticate — every read path re-checks expiry.
    """
    now = utc_now()
    removed = 0
    for model in (UserSession, LoginChallenge, PasswordResetToken, GoogleLoginNonce):
        result = await db.execute(delete(model).where(model.expires_at <= now))
        removed += result.rowcount or 0
    await db.commit()
    return removed


async def require_owner(
    request: Request,
    context: Annotated[AuthContext, Depends(require_authenticated)],
) -> AuthContext:
    """Owner-gated endpoints (invite management)."""
    if context.user.role != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    return context
