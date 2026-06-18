"""FastAPI application factory.

Wires: structured logging, request IDs, optional API-key auth, per-IP rate
limiting, SQLite history persistence, SSE streaming, and dependency-aware
health checks.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.limiter import limiter
from app.middleware import ApiKeyAuthMiddleware, RequestIdMiddleware
from app.observability.logging import configure_logging, get_logger
from app.persistence.db import init_db
from app.routers import filings, health, research


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
            "auth_enabled": bool(settings.verdict_api_key),
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
    )

    # Starlette runs the last-added middleware first. Desired stack:
    # RequestId -> CORS -> API key auth -> routes.
    app.add_middleware(ApiKeyAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Cost-USD", "X-Duration-Ms"],
    )
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
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation error",
                "errors": exc.errors(),
                "request_id": getattr(request.state, "request_id", ""),
            },
        )

    app.include_router(health.router)
    app.include_router(filings.router, prefix="/filings", tags=["filings"])
    app.include_router(research.router, prefix="/research", tags=["research"])

    return app


app = create_app()
