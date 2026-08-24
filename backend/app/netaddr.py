"""Resolve the real client IP behind a reverse proxy.

`X-Forwarded-For` is a request header, so it is attacker-controlled unless the
connection came from a proxy we trust. Everything that keys off a client
address — the per-IP rate limits guarding login, 2FA, and password reset, plus
the addresses written to the audit log — resolves through here.

Rules:
  * If the TCP peer is not a configured trusted proxy, the header is ignored
    entirely and the peer address is used.
  * If it is, the chain is walked right-to-left and the first address that is
    not itself a trusted proxy wins. nginx appends the true peer to whatever
    the client sent (`X-Forwarded-For $proxy_add_x_forwarded_for`), so a
    spoofed prefix is always to the *left* of the real address and loses.

TRUSTED_PROXY_IPS defaults to loopback plus the RFC1918 / unique-local ranges,
which is where a reverse proxy actually sits. A request arriving straight from
the public internet has a public peer address, so its header is never trusted.
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache

from fastapi import Request

from app.config import get_settings
from app.observability.logging import get_logger

log = get_logger(__name__)

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=8)
def _trusted_networks(raw: str) -> tuple[_Network, ...]:
    """Parse the comma-separated TRUSTED_PROXY_IPS setting into networks."""
    networks: list[_Network] = []
    for entry in raw.split(","):
        candidate = entry.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            log.warning("trusted_proxy_entry_invalid", extra={"entry": candidate})
    return tuple(networks)


def _normalize_host(raw: str) -> str:
    """Strip the port/brackets some proxies add: '1.2.3.4:5678', '[::1]:5678'."""
    host = raw.strip()
    if host.startswith("[") and "]" in host:
        return host[1 : host.index("]")]
    if host.count(":") == 1 and "." in host:
        return host.split(":", 1)[0]
    return host


def _is_trusted(host: str, networks: tuple[_Network, ...]) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in networks)


def client_ip(request: Request) -> str:
    """The address to attribute this request to. Never trusts a raw header."""
    peer = _normalize_host((request.client.host if request.client else "") or "")
    networks = _trusted_networks(get_settings().trusted_proxy_ips)
    if not networks or not _is_trusted(peer, networks):
        return peer

    forwarded = request.headers.get("x-forwarded-for") or ""
    for entry in reversed(forwarded.split(",")):
        candidate = _normalize_host(entry)
        if candidate and not _is_trusted(candidate, networks):
            return candidate
    # Every hop was a trusted proxy (or the header was absent).
    return peer
