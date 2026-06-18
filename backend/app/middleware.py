"""HTTP middlewares: request IDs, structured access logging, error envelope, auth."""

from __future__ import annotations

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
        rid = request.headers.get(self.HEADER) or uuid.uuid4().hex
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


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Optional X-API-Key gate.

    Active iff `VERDICT_API_KEY` is set. Skipped paths: /health*, /docs,
    /redoc, /openapi.json so the readiness probe and docs are always usable.
    """

    HEADER = "x-api-key"
    OPEN_PATHS = ("/health", "/docs", "/redoc", "/openapi.json")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        expected = get_settings().verdict_api_key
        if not expected:
            return await call_next(request)

        if any(request.url.path.startswith(p) for p in self.OPEN_PATHS):
            return await call_next(request)

        provided = request.headers.get(self.HEADER)
        if not provided or provided != expected:
            log.warning(
                "auth_rejected",
                extra={"path": request.url.path, "has_header": bool(provided)},
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Missing or invalid X-API-Key",
                    "request_id": getattr(request.state, "request_id", ""),
                },
            )

        return await call_next(request)
