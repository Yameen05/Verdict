"""Structured JSON logging with per-request correlation IDs.

Drops a JSON line for every log call carrying:

  - timestamp (UTC ISO8601)
  - level
  - logger name
  - message
  - request_id (from ContextVar, empty outside a request)
  - any extra={...} fields the call site supplies

Configure once at startup via `configure_logging()`. Use `get_logger(__name__)`
in any module. Request middleware (see app.middleware) sets the ContextVar.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Populated by RequestIdMiddleware.
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def set_request_id(rid: str) -> None:
    _request_id_ctx.set(rid)


def get_request_id() -> str:
    return _request_id_ctx.get()


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = _request_id_ctx.get()
        if rid:
            payload["request_id"] = rid
        # Capture any extra={} fields passed by the caller.
        for k, v in record.__dict__.items():
            if k in self._RESERVED or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        if record.exc_info:
            payload["stack"] = [{"file": frame.filename, "line": frame.lineno, "function": frame.name}
                                for frame in traceback.extract_tb(record.exc_info[2])]
            payload["error_type"] = record.exc_info[0].__name__
        encoded = json.dumps(payload, default=str)
        # Redact configured credentials even when an upstream exception or URL
        # was supplied via an extra field. Never serialize exception messages.
        from app.config import get_settings
        settings = get_settings()
        for name in type(settings).model_fields:
            if any(part in name for part in ("api_key", "password", "bootstrap_token")):
                value = getattr(settings, name)
                if isinstance(value, str) and value:
                    encoded = encoded.replace(json.dumps(value)[1:-1], "[REDACTED]")
        encoded = re.sub(r"(?i)(apiKey|api_key|token|key|password)=([^&\s\"]+)",
                         r"\1=[REDACTED]", encoded)
        return encoded


def configure_logging(level: str = "INFO") -> None:
    """Wire stdlib logging once. Idempotent."""
    root = logging.getLogger()
    # Clear any handlers uvicorn may have already installed so we don't double-log.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Tone down noisy loggers.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class TimedBlock:
    """Context manager that logs duration_ms on exit. Use for high-value ops."""

    def __init__(self, logger: logging.Logger, msg: str, **extra: Any):
        self.logger = logger
        self.msg = msg
        self.extra = extra
        self._start = 0.0

    def __enter__(self) -> TimedBlock:
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        duration_ms = round((time.perf_counter() - self._start) * 1000, 2)
        if exc:
            self.logger.exception(
                self.msg, extra={**self.extra, "duration_ms": duration_ms, "ok": False}
            )
        else:
            self.logger.info(
                self.msg, extra={**self.extra, "duration_ms": duration_ms, "ok": True}
            )
