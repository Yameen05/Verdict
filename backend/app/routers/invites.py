"""Invite-code registration — the $0 path to multi-user.

The owner mints one-time codes (only a SHA-256 digest is stored); a friend
redeems a code with an email + password to create a member account. No email
service required: possession of a valid code IS the verification.

Mounted under /auth. Endpoints:
  POST   /auth/invites        (owner)  mint a code — plaintext returned once
  GET    /auth/invites        (owner)  list codes and their status
  DELETE /auth/invites/{id}   (owner)  revoke an unused code
  POST   /auth/register       (public) redeem a code, create account + session
"""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.limiter import limiter
from app.persistence.db import Invite, User, session_scope
from app.security import (
    AuthContext,
    as_utc,
    basic_auth_payload,
    create_session,
    hash_password,
    normalize_email,
    record_audit,
    require_owner,
    set_session_cookie,
    token_digest,
    utc_now,
    validate_password,
)

router = APIRouter()

INVITE_TTL_DAYS = 7


class InviteCreateRequest(BaseModel):
    note: str = Field(default="", max_length=120)


class RegisterRequest(BaseModel):
    # Optional when PUBLIC_SIGNUP_ENABLED=true; required (and validated)
    # whenever a code is supplied.
    invite_code: str | None = Field(default=None, min_length=8, max_length=128)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)


def _invite_status(invite: Invite) -> str:
    if invite.used_at is not None:
        return "used"
    if as_utc(invite.expires_at) <= utc_now():
        return "expired"
    return "pending"


@router.post("/invites", status_code=201)
async def create_invite(
    request: Request,
    body: InviteCreateRequest,
    context: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(session_scope),
) -> dict:
    code = secrets.token_urlsafe(18)
    invite = Invite(
        code_hash=token_digest(code),
        note=body.note.strip(),
        created_by=context.user.id,
        expires_at=utc_now() + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invite)
    await db.flush()
    await record_audit(
        db, request, "invite_created", user_id=context.user.id,
        details={"invite_id": invite.id},
    )
    await db.commit()
    # The plaintext code is shown exactly once — only its digest persists.
    return {
        "id": invite.id,
        "code": code,
        "note": invite.note,
        "expires_at": invite.expires_at,
    }


@router.get("/invites")
async def list_invites(
    _context: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(session_scope),
) -> dict:
    rows = (
        await db.execute(select(Invite).order_by(Invite.created_at.desc()).limit(50))
    ).scalars().all()
    used_by_ids = {r.used_by for r in rows if r.used_by}
    emails: dict[int, str] = {}
    if used_by_ids:
        users = (
            await db.execute(select(User).where(User.id.in_(used_by_ids)))
        ).scalars().all()
        emails = {u.id: u.email for u in users}
    return {
        "invites": [
            {
                "id": r.id,
                "note": r.note,
                "status": _invite_status(r),
                "created_at": r.created_at,
                "expires_at": r.expires_at,
                "used_by_email": emails.get(r.used_by) if r.used_by else None,
                "used_at": r.used_at,
            }
            for r in rows
        ]
    }


@router.delete("/invites/{invite_id}", status_code=204, response_class=Response)
async def revoke_invite(
    request: Request,
    invite_id: int,
    context: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(session_scope),
) -> Response:
    invite = await db.get(Invite, invite_id)
    if invite is None or invite.used_at is not None:
        raise HTTPException(status_code=404, detail="Invite not found or already used")
    await db.delete(invite)
    await record_audit(
        db, request, "invite_revoked", user_id=context.user.id,
        details={"invite_id": invite_id},
    )
    await db.commit()
    return Response(status_code=204)


@router.post("/register", status_code=201)
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    db: AsyncSession = Depends(session_scope),
) -> dict:
    settings = get_settings()
    code = (body.invite_code or "").strip()
    invite: Invite | None = None
    if code:
        invite = await db.scalar(
            select(Invite).where(Invite.code_hash == token_digest(code))
        )
        if invite is None or invite.used_at is not None or as_utc(invite.expires_at) <= utc_now():
            await record_audit(db, request, "register_failed", details={"reason": "bad_invite"})
            await db.commit()
            raise HTTPException(status_code=401, detail="Invalid or expired invite code")
    elif not settings.public_signup_enabled:
        await record_audit(db, request, "register_failed", details={"reason": "no_invite"})
        await db.commit()
        raise HTTPException(status_code=401, detail="An invite code is required to register")

    email = normalize_email(body.email)
    validate_password(body.password, email)

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        role="member",
        # Legacy databases have UNIQUE(singleton_key); members get random values.
        singleton_key=secrets.randbits(60),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from exc

    if invite is not None:
        invite.used_by = user.id
        invite.used_at = utc_now()

    user_session, raw_token = await create_session(
        db, request, user, mfa_verified=not settings.require_2fa
    )
    await record_audit(
        db, request, "member_registered", user_id=user.id,
        details={"invite_id": invite.id if invite else None, "public_signup": invite is None},
    )
    await db.commit()

    set_session_cookie(response, raw_token)
    return basic_auth_payload(AuthContext(user=user, session=user_session))
