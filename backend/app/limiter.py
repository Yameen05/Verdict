"""Shared slowapi Limiter instance.

Per-process in-memory backend by default. Set RATE_LIMIT_STORAGE_URI (e.g.
redis://localhost:6379/0) so all workers share one counter store when you
scale past a single backend process.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_settings().rate_limit_storage_uri.strip() or "memory://",
)
