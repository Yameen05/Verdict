"""HTTP middlewares: request IDs, origin checks, headers, logging, error envelope."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings
from app.observability.logging import get_logger, set_request_id

log = get_logger("app.http")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Read or generate an X-Request-ID header and bind it to the log context."""

    HEADER = "x-request-id"

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        candidate = (request.headers.get(self.HEADER) or "")[:64]
        rid = candidate if re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", candidate) else uuid.uuid4().hex
        set_request_id(rid)
        request.state.request_id = rid

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as e:  # noqa: BLE001 - centralized handler
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log.exception(
                "request_unhandled",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                },
            )
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": rid,
                },
                headers={self.HEADER: rid},
            )

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[self.HEADER] = rid
        log.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


class OriginProtectionMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin browser writes before they reach authentication."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            allowed = set(get_settings().cors_origins_list)
            if origin and origin not in allowed:
                log.warning("origin_rejected", extra={"path": request.url.path})
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Origin is not allowed",
                        "request_id": getattr(request.state, "request_id", ""),
                    },
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defense-in-depth headers for API responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("Cache-Control", "no-store")
        if get_settings().docs_enabled and request.url.path in {"/docs", "/redoc"}:
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "frame-ancestors 'none'",
            )
        else:
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'",
            )
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        if get_settings().session_cookie_secure:
            headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
