"""Email-based password reset (account recovery).

Mounted under /auth. The request endpoint never reveals whether an account
exists; a link is emailed only when SMTP is configured. Tokens are random,
stored as SHA-256 digests, single-use, and short-lived. A successful reset
revokes every session, login challenge, and outstanding reset token for the
account — but leaves 2FA enrollment intact.

  POST /auth/password-reset/request   {email}            → always 204
  POST /auth/password-reset/confirm   {token, password}  → 204 or 401
"""

import asyncio
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.limiter import limiter
from app.persistence.db import (
    LoginChallenge,
    PasswordResetToken,
    User,
    UserSession,
    session_scope,
)
from app.security import (
    as_utc,
    hash_password,
    new_token,
    normalize_email,
    record_audit,
    token_digest,
    utc_now,
    validate_password,
)
from app.services.mailer import email_configured, send_email

router = APIRouter()


class ResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=12, max_length=128)


def _reset_email_body(link: str, minutes: int) -> str:
    return (
        "A password reset was requested for your Verdict account.\n\n"
        f"Reset link (valid for {minutes} minutes, single use):\n{link}\n\n"
        "If you did not request this, you can ignore this email — your "
        "password is unchanged."
    )


@router.post(
    "/password-reset/request",
    status_code=204,
    response_class=Response,
    response_model=None,
)
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def request_password_reset(
    request: Request,
    body: ResetRequest,
    db: AsyncSession = Depends(session_scope),
) -> Response:
    settings = get_settings()
    email = normalize_email(body.email)
    user = await db.scalar(select(User).where(User.email == email))

    # Same response whether or not the account exists (no enumeration).
    if user is None or not user.is_active or not email_configured():
        await record_audit(
            db, request, "password_reset_requested",
            details={"delivered": False},
        )
        await db.commit()
        return Response(status_code=204)

    await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    raw_token = new_token()
    db.add(
        PasswordResetToken(
            token_hash=token_digest(raw_token),
            user_id=user.id,
            expires_at=utc_now()
            + timedelta(minutes=settings.password_reset_token_minutes),
        )
    )
    await record_audit(
        db, request, "password_reset_requested",
        user_id=user.id, details={"delivered": True},
    )
    await db.commit()

    link = f"{settings.password_reset_link_base}/?reset_token={raw_token}"
    await asyncio.to_thread(
        send_email,
        user.email,
        "Reset your Verdict password",
        _reset_email_body(link, settings.password_reset_token_minutes),
    )
    return Response(status_code=204)


@router.post(
    "/password-reset/confirm",
    status_code=204,
    response_class=Response,
    response_model=None,
)
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def confirm_password_reset(
    request: Request,
    body: ResetConfirm,
    db: AsyncSession = Depends(session_scope),
) -> Response:
    result = await db.execute(
        select(PasswordResetToken, User)
        .join(User, User.id == PasswordResetToken.user_id)
        .where(PasswordResetToken.token_hash == token_digest(body.token))
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired reset link")
    token, user = row
    if as_utc(token.expires_at) <= utc_now() or not user.is_active:
        await db.delete(token)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired reset link")

    validate_password(body.password, user.email)
    user.password_hash = hash_password(body.password)

    # Revoke everything that could still authenticate as this user.
    await db.execute(
        delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    await db.execute(delete(LoginChallenge).where(LoginChallenge.user_id == user.id))
    await record_audit(db, request, "password_reset_completed", user_id=user.id)
    await db.commit()
    return Response(status_code=204)
