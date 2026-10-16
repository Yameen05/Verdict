"""ASGI admission, body limits, and whole-request deadlines, including SSE.

The supported deployment uses one worker. No wait queue is allocated when
busy, so bursts cannot grow an unbounded backlog of upstream requests.
"""

import asyncio

from starlette.responses import JSONResponse

from app.config import get_settings


class ResourceLimitsMiddleware:
    def __init__(self, app):
        self.app = app
        self.active = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = get_settings()
        path = scope.get("path", "")
        expensive = path.startswith(("/research", "/filings", "/market", "/daytrade", "/me/practice")) or path.startswith("/auth") or path == "/health/ready"
        if expensive and self.active >= settings.max_concurrent_requests:
            await JSONResponse({"detail": "Server is busy. Please retry shortly"}, 503,
                               headers={"Retry-After": "5"})(scope, receive, send)
            return
        if expensive:
            self.active += 1
        started = False
        complete = False

        async def tracked_send(message):
            nonlocal started, complete
            if message["type"] == "http.response.start":
                started = True
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                complete = True
            await send(message)

        try:
            # A chunked body cannot bypass Content-Length checks. Retain at
            # most the configured cap, then replay once to the downstream app.
            body = bytearray()
            async with asyncio.timeout(15):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    part = message.get("body", b"")
                    if len(body) + len(part) > settings.max_request_bytes:
                        await JSONResponse({"detail": "Request body too large"}, 413)(scope, receive, send)
                        return
                    body.extend(part)
                    if not message.get("more_body", False):
                        break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            async with asyncio.timeout(settings.request_timeout_seconds):
                await self.app(scope, replay, tracked_send)
        except TimeoutError:
            if not started:
                await JSONResponse({"detail": "Request timed out"}, 504)(scope, receive, send)
            elif complete:
                pass  # Background work timed out after the response was sent.
            elif path.endswith("/stream"):
                await send({"type": "http.response.body", "body": b'event: error\ndata: {"detail":"Research timed out","error_type":"TimeoutError"}\n\n', "more_body": False})
            else:
                await send({"type": "http.response.body", "body": b"", "more_body": False})
        finally:
            if expensive:
                self.active -= 1
