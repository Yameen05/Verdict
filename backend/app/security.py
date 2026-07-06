"""Authentication primitives and FastAPI dependencies.

The browser receives only a random, HttpOnly session token. The database stores
its SHA-256 digest, so a database read alone cannot be used to hijack a session.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.observability.logging import get_request_id
from app.persistence.db import AuditEvent, User, UserSession, session_scope

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
_RECOVERY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


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


def validate_password(password: str, email: str = "") -> None:
    if len(password) < 12:
        raise HTTPException(status_code=422, detail="Password must be at least 12 characters")
    if len(password) > 128:
        raise HTTPException(status_code=422, detail="Password must be at most 128 characters")
    local_part = email.split("@", 1)[0].lower()
    if local_part and len(local_part) >= 4 and local_part in password.lower():
        raise HTTPException(status_code=422, detail="Password must not contain your email name")


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(stored_hash: str | None, candidate: str) -> bool:
    target = stored_hash or _DUMMY_PASSWORD_HASH
    try:
        return PASSWORD_HASHER.verify(target, candidate)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(stored_hash: str) -> bool:
    return PASSWORD_HASHER.check_needs_rehash(stored_hash)


def new_token(byte_length: int = 32) -> str:
    return secrets.token_urlsafe(byte_length)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fernet() -> Fernet:
    raw = get_settings().auth_encryption_key.strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUTH_ENCRYPTION_KEY is not configured",
        )
    try:
        return Fernet(raw.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUTH_ENCRYPTION_KEY is invalid",
        ) from exc


def encrypt_totp_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_totp_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stored 2FA configuration cannot be decrypted",
        ) from exc


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [
        "-".join(
            "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))
            for _ in range(3)
        )
        for _ in range(count)
    ]


def normalize_recovery_code(code: str) -> str:
    return "".join(c for c in code.upper() if c in string.ascii_uppercase + string.digits)


def recovery_code_digest(code: str) -> str:
    key_material = get_settings().auth_encryption_key.strip().encode("utf-8")
    key = hashlib.sha256(b"verdict-recovery-codes:" + key_material).digest()
    return hmac.new(
        key,
        normalize_recovery_code(code).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def request_ip(request: Request) -> str:
    return ((request.client.host if request.client else "") or "")[:64]


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
    *,
    mfa_verified: bool,
) -> tuple[UserSession, str]:
    settings = get_settings()
    raw_token = new_token()
    now = utc_now()
    row = UserSession(
        token_hash=token_digest(raw_token),
        user_id=user.id,
        csrf_token=new_token(24),
        mfa_verified=mfa_verified,
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
    if not secrets.compare_digest(provided, context.session.csrf_token):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


async def require_authenticated(
    request: Request,
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthContext:
    verify_csrf(request, context)
    if not context.session.mfa_verified:
        raise HTTPException(status_code=403, detail="Two-factor authentication setup required")
    return context


def basic_auth_payload(context: AuthContext) -> dict:
    return {
        "user": {
            "id": context.user.id,
            "email": context.user.email,
            "two_factor_enabled": context.user.totp_enabled,
        },
        "csrf_token": context.session.csrf_token,
        "requires_2fa_setup": not context.session.mfa_verified,
    }
