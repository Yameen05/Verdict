"""The per-IP auth rate limit must survive a forged X-Forwarded-For.

The limiter is what stands between an attacker and unlimited password/TOTP
guesses, so the address it keys on cannot be client-supplied.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.limiter import limiter
from app.netaddr import _trusted_networks

BAD_LOGIN = {"email": "owner@example.com", "password": "not-the-right-password"}


@pytest.fixture
def strict_limit(monkeypatch):
    """Three auth attempts a minute, behind a proxy on a trusted address."""
    monkeypatch.setenv("RATE_LIMIT_AUTH", "3/minute")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8")
    get_settings.cache_clear()
    _trusted_networks.cache_clear()
    limiter.reset()
    yield
    limiter.reset()
    _trusted_networks.cache_clear()
    get_settings.cache_clear()


def _proxied_client() -> TestClient:
    """A client whose TCP peer is the reverse proxy, as in the compose setup."""
    from app.main import create_app

    return TestClient(create_app(), client=("10.0.0.2", 5555))


def _statuses(client: TestClient, forwarded: list[str]) -> list[int]:
    return [
        client.post("/auth/login", json=BAD_LOGIN, headers={"X-Forwarded-For": xff}).status_code
        for xff in forwarded
    ]


def test_rotating_a_forged_prefix_cannot_escape_the_limit(strict_limit):
    """nginx appends the real peer, so the forged hops on the left are ignored."""
    with _proxied_client() as client:
        # One attacker at 203.0.113.9 forging a different origin each request.
        statuses = _statuses(
            client,
            [f"198.51.100.{n}, 203.0.113.9" for n in range(1, 7)],
        )
    assert statuses[:3] == [401, 401, 401]
    assert 429 in statuses[3:], statuses


def test_distinct_real_clients_keep_separate_buckets(strict_limit):
    """The fix must not collapse every user behind the proxy into one counter."""
    with _proxied_client() as client:
        statuses = _statuses(client, [f"203.0.113.{n}" for n in range(1, 7)])
    assert statuses == [401] * 6, statuses


def test_header_is_ignored_when_the_peer_is_not_a_trusted_proxy(strict_limit):
    """A client reaching the app directly cannot claim an address at all."""
    from app.main import create_app

    with TestClient(create_app(), client=("203.0.113.9", 5555)) as client:
        statuses = _statuses(client, [f"198.51.100.{n}" for n in range(1, 7)])
    assert statuses[:3] == [401, 401, 401]
    assert 429 in statuses[3:], statuses
