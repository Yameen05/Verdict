"""Password authentication and server-side sessions."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.limiter import limiter
from app.persistence.db import User, UserSession, session_scope
from app.security import (
    AuthContext,
    basic_auth_payload,
    clear_session_cookie,
    create_session,
    get_auth_context,
    hash_password,
    normalize_email,
    password_needs_rehash,
    record_audit,
    set_session_cookie,
    utc_now,
    validate_password,
    verify_csrf,
    verify_password,
)
from app.services.budgets import reserve_auth_attempt
from app.services.mailer import email_configured

router = APIRouter()


class BootstrapRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=15, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


@router.get("/status")
async def auth_status(db: AsyncSession = Depends(session_scope)) -> dict:
    count = await db.scalar(select(func.count(User.id)).where(User.role == "owner"))
    settings = get_settings()
    return {
        "bootstrap_required": count == 0,
        "public_signup_enabled": settings.public_signup_enabled,
        # The forgot-password flow only works when the server can send email.
        "password_reset_available": email_configured(),
        "google_client_id": settings.google_client_id.strip() or None,
    }


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
    if not configured or not secrets.compare_digest(provided.encode("utf-8"), configured.encode("utf-8")):
        # Do not reveal whether the server has a bootstrap token configured.
        raise HTTPException(status_code=404, detail="Not found")

    count = await db.scalar(select(func.count(User.id)).where(User.role == "owner"))
    if count:
        raise HTTPException(status_code=404, detail="Not found")

    email = normalize_email(body.email)
    validate_password(body.password)
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
    await reserve_auth_attempt(email, "login", 10, 900)
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

    user.last_login_at = utc_now()
    user_session, raw_token = await create_session(
        db,
        request,
        user,
    )
    await record_audit(db, request, "login_succeeded", user_id=user.id)
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
