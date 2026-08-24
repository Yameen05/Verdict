"""Shared slowapi Limiter instance.

Per-process in-memory backend by default. Set RATE_LIMIT_STORAGE_URI (e.g.
redis://localhost:6379/0) so all workers share one counter store when you
scale past a single backend process.

Requests are keyed by `app.netaddr.client_ip`, not by the raw socket peer:
behind a reverse proxy every request shares the proxy's address, and a raw
X-Forwarded-For is client-controlled. See that module for the trust rules.

Buckets are scoped per endpoint, not per URL. slowapi's default ("url") puts
the concrete request path in the bucket key, so a route with a path parameter —
/research/{ticker}, /daytrade/{ticker}/signal — hands the caller a fresh counter
for every ticker and its limit never binds.
"""

from __future__ import annotations

from slowapi import Limiter

from app.config import get_settings
from app.netaddr import client_ip

limiter = Limiter(
    key_func=client_ip,
    key_style="endpoint",
    storage_uri=get_settings().rate_limit_storage_uri.strip() or "memory://",
)
