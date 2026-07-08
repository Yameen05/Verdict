"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.limiter import limiter
from app.middleware import (
    OriginProtectionMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from app.observability.logging import configure_logging, get_logger
from app.persistence.db import init_db
from app.routers import ask, auth, filings, health, invites, research, scoreboard
from app.security import require_authenticated


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(level=settings.log_level)
    log = get_logger("app.lifespan")
    log.info(
        "startup",
        extra={
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "auth_enabled": True,
            "database_url": settings.database_url.split("@")[-1],  # hide creds if any
        },
    )
    await init_db()
    log.info("db_ready")
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Verdict API",
        version="1.0.0",
        description=(
            "Multi-agent financial research. SEC filings (RAG) + News sentiment "
            "(NewsAPI + VADER) + Financials (yfinance) → Buy/Hold/Sell report."
        ),
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    # Starlette runs the last-added middleware first.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(OriginProtectionMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-Bootstrap-Token",
            "X-CSRF-Token",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID", "X-Cost-USD", "X-Duration-Ms"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
    app.add_middleware(RequestIdMiddleware)

    # Rate limiter: attach to app and wire its 429 handler.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Centralized HTTPException handler that always includes request_id.
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "request_id": getattr(request.state, "request_id", ""),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # Pydantic's raw validation errors can include the rejected input.  Do
        # not reflect passwords, OTPs, bootstrap tokens, or other request data
        # back to clients.
        safe_errors = [
            {
                "type": error.get("type", "validation_error"),
                "loc": error.get("loc", ()),
                "msg": error.get("msg", "Invalid value"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation error",
                "errors": safe_errors,
                "request_id": getattr(request.state, "request_id", ""),
            },
        )

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/auth", tags=["authentication"])
    app.include_router(invites.router, prefix="/auth", tags=["authentication"])
    protected = [Depends(require_authenticated)]
    app.include_router(
        filings.router,
        prefix="/filings",
        tags=["filings"],
        dependencies=protected,
    )
    # ask.router must register before research.router: its literal /ask path
    # would otherwise be swallowed by research's POST /{ticker}.
    app.include_router(
        ask.router,
        prefix="/research",
        tags=["research"],
        dependencies=protected,
    )
    app.include_router(
        research.router,
        prefix="/research",
        tags=["research"],
        dependencies=protected,
    )
    app.include_router(
        scoreboard.router,
        prefix="/research",
        tags=["scoreboard"],
        dependencies=protected,
    )

    return app


app = create_app()
