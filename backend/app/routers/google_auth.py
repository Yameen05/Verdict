"""Google Identity Services login using the same sessions as password login."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.auth.exceptions import GoogleAuthError, TransportError
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.limiter import limiter
from app.persistence.db import GoogleIdentity, GoogleLoginNonce, Invite, User, session_scope
from app.security import (
    AuthContext,
    as_utc,
    basic_auth_payload,
    create_session,
    get_auth_context,
    new_token,
    normalize_email,
    record_audit,
    set_session_cookie,
    token_digest,
    utc_now,
    verify_csrf,
)
from app.services.budgets import reserve_auth_attempt
from app.services.google_sign_in import verify_google_credential
from app.services.legal_agreements import (
    LegalAcceptance,
    record_acceptance,
    require_current_acceptance,
)

router = APIRouter()
NONCE_TTL_SECONDS = 600


class GoogleLoginRequest(BaseModel):
    legal_acceptance: LegalAcceptance | None = None
    credential: str = Field(min_length=1, max_length=16384)
    invite_code: str = Field(default="", max_length=256)


def _client_id() -> str:
    client_id = get_settings().google_client_id.strip()
    if not client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    return client_id


def _cookie_name() -> str:
    prefix = "__Host-" if get_settings().session_cookie_secure else ""
    return f"{prefix}verdict_google_nonce"


@router.get("/google/nonce")
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def google_nonce(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(session_scope),
) -> dict:
    _client_id()
    raw_token = new_token()
    digest = token_digest(raw_token)
    now = utc_now()
    # Bound abandoned challenges, and retire this browser's previous challenge.
    await db.execute(delete(GoogleLoginNonce).where(GoogleLoginNonce.expires_at <= now))
    previous = request.cookies.get(_cookie_name())
    if previous:
        await db.execute(
            delete(GoogleLoginNonce).where(GoogleLoginNonce.token_hash == token_digest(previous))
        )
    db.add(GoogleLoginNonce(
        token_hash=digest, expires_at=now + timedelta(seconds=NONCE_TTL_SECONDS)
    ))
    await db.commit()
    response.set_cookie(
        _cookie_name(), raw_token, max_age=NONCE_TTL_SECONDS,
        secure=get_settings().session_cookie_secure, httponly=True, samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"nonce": digest}


@router.post("/google")
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def google_login(
    request: Request,
    response: Response,
    body: GoogleLoginRequest,
    db: AsyncSession = Depends(session_scope),
) -> dict:
    client_id = _client_id()
    raw_token = request.cookies.get(_cookie_name(), "")
    if not raw_token:
        raise HTTPException(status_code=403, detail="Restart Google sign-in and try again")
    nonce = token_digest(raw_token)
    # DELETE ... RETURNING makes each challenge single-use across workers.
    consumed = await db.scalar(
        delete(GoogleLoginNonce).where(
            GoogleLoginNonce.token_hash == nonce,
            GoogleLoginNonce.expires_at > utc_now(),
        ).returning(GoogleLoginNonce.token_hash)
    )
    await db.commit()
    if consumed is None:
        raise HTTPException(status_code=403, detail="Google sign-in expired. Please try again")
    try:
        claims = await verify_google_credential(body.credential, client_id)
    except TransportError as exc:
        raise HTTPException(status_code=503, detail="Google sign-in is temporarily unavailable") from exc
    except (ValueError, GoogleAuthError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Google sign-in. Please try again") from exc

    token_nonce = claims.get("nonce")
    subject = claims.get("sub")
    if not isinstance(token_nonce, str) or not secrets.compare_digest(token_nonce.encode("utf-8"), nonce.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Restart Google sign-in and try again")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
        raise HTTPException(status_code=401, detail="Invalid Google account")
    if claims.get("email_verified") is not True or not isinstance(claims.get("email"), str):
        raise HTTPException(status_code=401, detail="Google must verify your email before you sign in")
    email = normalize_email(claims["email"])
    identity = await db.get(GoogleIdentity, subject)
    user = await db.get(User, identity.user_id) if identity else None
    new_account = False
    invite = None
    if identity is None:
        user = await db.scalar(select(User).where(User.email == email))
        if user is not None:
            # Only Google-hosted email proves current ownership. A verified
            # third-party email may have changed owners since Google verified it.
            authoritative = email.endswith("@gmail.com") or bool(claims.get("hd"))
            # Password signup does not verify email. A pre-registered password
            # must not retain access after the real email owner uses Google.
            # Linking therefore requires proof of the existing account as well.
            try:
                existing_auth = await get_auth_context(request, db)
                verify_csrf(request, existing_auth)
                same_account = existing_auth.user.id == user.id
            except HTTPException:
                same_account = False
            linked = await db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
            if not authoritative or not same_account or linked is not None:
                raise HTTPException(
                    status_code=409,
                    detail="This email already has an account. Use its existing sign-in method.",
                )
        else:
            if not await db.scalar(select(func.count(User.id)).where(User.role == "owner")):
                raise HTTPException(status_code=403, detail="The owner must finish account setup first")
            code = body.invite_code.strip()
            if code:
                invite = await db.scalar(select(Invite).where(Invite.code_hash == token_digest(code)))
                if invite is None or invite.used_at is not None or as_utc(invite.expires_at) <= utc_now():
                    raise HTTPException(status_code=401, detail="Invalid or expired invite code")
            elif not get_settings().public_signup_enabled:
                raise HTTPException(status_code=401, detail="An invite code is required to register")
            require_current_acceptance(body.legal_acceptance)
            await reserve_auth_attempt("global-registration", "signup", 100, 86400)
            user = User(
                # Empty hash disables password login for Google-only accounts.
                email=email, password_hash="", role="member", singleton_key=secrets.randbits(60)  # nosec B106
            )
            db.add(user)
            new_account = True
        if not user.is_active and not new_account:
            raise HTTPException(status_code=401, detail="This account is inactive")
        try:
            await db.flush()
            db.add(GoogleIdentity(subject=subject, user_id=user.id))
            await db.flush()
            if invite is not None:
                redeemed = await db.execute(
                    update(Invite).where(
                        Invite.id == invite.id, Invite.used_at.is_(None), Invite.expires_at > utc_now(),
                    ).values(used_by=user.id, used_at=utc_now())
                    .execution_options(synchronize_session=False)
                )
                if redeemed.rowcount != 1:
                    await db.rollback()
                    raise HTTPException(status_code=401, detail="Invalid or expired invite code")
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Account changed. Please try signing in again") from exc

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="This account is inactive")
    if new_account:
        await record_acceptance(db, request, user.id)
    user.last_login_at = utc_now()
    user_session, raw_session = await create_session(db, request, user)
    await record_audit(
        db, request, "google_signup_succeeded" if new_account else "google_login_succeeded",
        user_id=user.id,
    )
    await db.commit()
    set_session_cookie(response, raw_session)
    response.delete_cookie(
        _cookie_name(), secure=get_settings().session_cookie_secure,
        httponly=True, samesite="strict", path="/",
    )
    return basic_auth_payload(AuthContext(user=user, session=user_session))
