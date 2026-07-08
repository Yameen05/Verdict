"""Owner authentication, mandatory TOTP enrollment, and recovery-code login."""

import base64
import io
import secrets
import time
from datetime import timedelta

import pyotp
import segno
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.limiter import limiter
from app.persistence.db import LoginChallenge, User, UserSession, session_scope
from app.security import (
    AuthContext,
    as_utc,
    basic_auth_payload,
    clear_session_cookie,
    create_session,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_recovery_codes,
    get_auth_context,
    hash_password,
    new_token,
    normalize_email,
    password_needs_rehash,
    record_audit,
    recovery_code_digest,
    set_session_cookie,
    token_digest,
    utc_now,
    validate_password,
    verify_csrf,
    verify_password,
)

router = APIRouter()


class BootstrapRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ChallengeRequest(BaseModel):
    challenge_token: str = Field(min_length=32, max_length=256)
    code: str = Field(min_length=6, max_length=32)


class TotpCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


def _totp_counter_for_code(totp: pyotp.TOTP, code: str) -> int | None:
    current = int(time.time()) // totp.interval
    normalized = "".join(c for c in code if c.isdigit())
    for counter in range(current - 1, current + 2):
        if secrets.compare_digest(totp.at(counter * totp.interval), normalized):
            return counter
    return None


def _qr_data_uri(uri: str) -> str:
    output = io.BytesIO()
    segno.make(uri, micro=False).save(
        output,
        kind="svg",
        scale=5,
        border=2,
        dark="#0f172a",
        light="#ffffff",
    )
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


@router.get("/status")
async def auth_status(db: AsyncSession = Depends(session_scope)) -> dict:
    count = await db.scalar(select(func.count(User.id)))
    return {"bootstrap_required": count == 0}


@router.post("/bootstrap", status_code=201)
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def bootstrap(
    request: Request,
    response: Response,
    body: BootstrapRequest,
    db: AsyncSession = Depends(session_scope),
) -> dict:
    settings = get_settings()
    configured = settings.auth_bootstrap_token.strip()
    provided = request.headers.get("x-bootstrap-token", "")
    if not configured or not secrets.compare_digest(provided, configured):
        # Do not reveal whether the server has a bootstrap token configured.
        raise HTTPException(status_code=404, detail="Not found")

    count = await db.scalar(select(func.count(User.id)))
    if count:
        raise HTTPException(status_code=404, detail="Not found")

    email = normalize_email(body.email)
    validate_password(body.password, email)
    user = User(email=email, password_hash=hash_password(body.password), role="owner")
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Owner account already exists") from exc

    user_session, raw_token = await create_session(
        db,
        request,
        user,
        mfa_verified=not settings.require_2fa,
    )
    await record_audit(db, request, "owner_bootstrapped", user_id=user.id)
    await db.commit()
    set_session_cookie(response, raw_token)
    return basic_auth_payload(AuthContext(user=user, session=user_session))


@router.post("/login")
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: AsyncSession = Depends(session_scope),
) -> dict:
    email = normalize_email(body.email)
    user = await db.scalar(select(User).where(User.email == email))
    valid = verify_password(user.password_hash if user else None, body.password)
    if user is None or not valid or not user.is_active:
        await record_audit(
            db,
            request,
            "login_failed",
            user_id=user.id if user else None,
            details={"reason": "invalid_credentials"},
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    settings = get_settings()
    if settings.require_2fa and user.totp_enabled:
        await db.execute(delete(LoginChallenge).where(LoginChallenge.user_id == user.id))
        raw_challenge = new_token()
        db.add(
            LoginChallenge(
                token_hash=token_digest(raw_challenge),
                user_id=user.id,
                expires_at=utc_now()
                + timedelta(minutes=settings.login_challenge_minutes),
            )
        )
        await record_audit(db, request, "password_verified", user_id=user.id)
        await db.commit()
        response.headers["Cache-Control"] = "no-store"
        return {"requires_2fa": True, "challenge_token": raw_challenge}

    user.last_login_at = utc_now()
    user_session, raw_token = await create_session(
        db,
        request,
        user,
        mfa_verified=not settings.require_2fa,
    )
    await record_audit(db, request, "login_succeeded", user_id=user.id)
    await db.commit()
    set_session_cookie(response, raw_token)
    return basic_auth_payload(AuthContext(user=user, session=user_session))


@router.post("/2fa/verify")
@limiter.limit(lambda: get_settings().rate_limit_auth)
async def verify_second_factor(
    request: Request,
    response: Response,
    body: ChallengeRequest,
    db: AsyncSession = Depends(session_scope),
) -> dict:
    result = await db.execute(
        select(LoginChallenge, User)
        .join(User, User.id == LoginChallenge.user_id)
        .where(LoginChallenge.token_hash == token_digest(body.challenge_token))
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired verification challenge")
    challenge, user = row
    if as_utc(challenge.expires_at) <= utc_now():
        await db.delete(challenge)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired verification challenge")
    if challenge.attempts >= 5 or not user.is_active or not user.totp_secret_encrypted:
        await db.delete(challenge)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired verification challenge")

    totp = pyotp.TOTP(decrypt_totp_secret(user.totp_secret_encrypted))
    counter = _totp_counter_for_code(totp, body.code)
    used_recovery = False
    valid = counter is not None and (
        user.totp_last_counter is None or counter > user.totp_last_counter
    )

    if not valid:
        digest = recovery_code_digest(body.code)
        if digest in (user.recovery_code_hashes or []):
            user.recovery_code_hashes = [
                stored for stored in user.recovery_code_hashes if stored != digest
            ]
            used_recovery = True
            valid = True

    if not valid:
        challenge.attempts += 1
        await record_audit(db, request, "two_factor_failed", user_id=user.id)
        if challenge.attempts >= 5:
            await db.delete(challenge)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid or expired verification code")

    if counter is not None:
        user.totp_last_counter = counter
    user.last_login_at = utc_now()
    await db.delete(challenge)
    user_session, raw_token = await create_session(db, request, user, mfa_verified=True)
    await record_audit(
        db,
        request,
        "login_succeeded",
        user_id=user.id,
        details={"recovery_code_used": used_recovery},
    )
    await db.commit()
    set_session_cookie(response, raw_token)
    return basic_auth_payload(AuthContext(user=user, session=user_session))


@router.get("/me")
async def me(context: AuthContext = Depends(get_auth_context)) -> dict:
    return basic_auth_payload(context)


@router.post("/logout", status_code=204, response_class=Response, response_model=None)
async def logout(
    request: Request,
    response: Response,
    context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(session_scope),
) -> Response:
    verify_csrf(request, context)
    await db.execute(
        delete(UserSession).where(UserSession.token_hash == context.session.token_hash)
    )
    await record_audit(db, request, "logout", user_id=context.user.id)
    await db.commit()
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.post("/2fa/setup")
async def setup_two_factor(
    request: Request,
    context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(session_scope),
) -> dict:
    verify_csrf(request, context)
    if context.user.totp_enabled:
        raise HTTPException(status_code=409, detail="Two-factor authentication is already enabled")

    if context.user.totp_secret_encrypted:
        secret = decrypt_totp_secret(context.user.totp_secret_encrypted)
    else:
        secret = pyotp.random_base32()
        context.user.totp_secret_encrypted = encrypt_totp_secret(secret)
        context.user.totp_last_counter = None
    await record_audit(db, request, "two_factor_setup_started", user_id=context.user.id)
    await db.commit()

    uri = pyotp.TOTP(secret).provisioning_uri(
        name=context.user.email,
        issuer_name="Verdict",
    )
    return {
        "secret": secret,
        "provisioning_uri": uri,
        "qr_code_data_uri": _qr_data_uri(uri),
    }


@router.post("/2fa/enable")
async def enable_two_factor(
    request: Request,
    body: TotpCodeRequest,
    context: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(session_scope),
) -> dict:
    verify_csrf(request, context)
    encrypted = context.user.totp_secret_encrypted
    if not encrypted or context.user.totp_enabled:
        raise HTTPException(status_code=409, detail="Start two-factor setup first")

    totp = pyotp.TOTP(decrypt_totp_secret(encrypted))
    counter = _totp_counter_for_code(totp, body.code)
    if counter is None:
        raise HTTPException(status_code=422, detail="Verification code is invalid")

    recovery_codes = generate_recovery_codes()
    context.user.totp_enabled = True
    context.user.totp_last_counter = counter
    context.user.recovery_code_hashes = [
        recovery_code_digest(code) for code in recovery_codes
    ]
    context.session.mfa_verified = True
    await record_audit(db, request, "two_factor_enabled", user_id=context.user.id)
    await db.commit()
    return {
        **basic_auth_payload(context),
        "recovery_codes": recovery_codes,
    }
