"""Client-IP resolution: X-Forwarded-For is believed only from a trusted peer."""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from app.config import get_settings
from app.netaddr import _trusted_networks, client_ip


def _request(peer: str, forwarded: str | None = None) -> Request:
    raw: list[tuple[bytes, bytes]] = []
    if forwarded is not None:
        raw.append((b"x-forwarded-for", forwarded.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": Headers(raw=raw).raw,
            "client": (peer, 12345),
        }
    )


@pytest.fixture(autouse=True)
def _clear_network_cache():
    _trusted_networks.cache_clear()
    get_settings.cache_clear()
    yield
    _trusted_networks.cache_clear()
    get_settings.cache_clear()


def test_untrusted_peer_header_is_ignored(monkeypatch):
    """The header is free-form input from a direct client — never believe it."""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8")
    assert client_ip(_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


def test_trusted_proxy_yields_the_forwarded_address(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8")
    assert client_ip(_request("10.1.2.3", "203.0.113.9")) == "203.0.113.9"


def test_spoofed_prefix_loses_to_the_address_the_proxy_appended(monkeypatch):
    """nginx appends the true peer, so a forged prefix is always to the left."""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8")
    request = _request("10.1.2.3", "8.8.8.8, 9.9.9.9, 203.0.113.9")
    assert client_ip(request) == "203.0.113.9"


def test_chained_trusted_proxies_are_skipped(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8,192.168.0.0/16")
    request = _request("10.1.2.3", "203.0.113.9, 192.168.1.5")
    assert client_ip(request) == "203.0.113.9"


def test_empty_trust_list_always_uses_the_peer(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "")
    assert client_ip(_request("127.0.0.1", "1.2.3.4")) == "127.0.0.1"


def test_missing_header_falls_back_to_the_peer(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8")
    assert client_ip(_request("10.1.2.3")) == "10.1.2.3"


def test_garbage_forwarded_entries_are_not_treated_as_addresses(monkeypatch):
    """A non-IP is untrusted, so it is returned rather than silently skipped."""
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8")
    assert client_ip(_request("10.1.2.3", "not-an-ip")) == "not-an-ip"


def test_ports_and_brackets_are_stripped(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "10.0.0.0/8")
    assert client_ip(_request("10.1.2.3", "203.0.113.9:5678")) == "203.0.113.9"
    assert client_ip(_request("10.1.2.3", "[2001:db8::1]:5678")) == "2001:db8::1"


def test_invalid_trust_entries_are_skipped_not_fatal(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "nonsense,10.0.0.0/8")
    assert client_ip(_request("10.1.2.3", "203.0.113.9")) == "203.0.113.9"


def test_default_trusts_the_private_ranges_a_proxy_sits_on():
    """Compose puts nginx on a bridge network, so this must work unconfigured."""
    networks = _trusted_networks(get_settings().trusted_proxy_ips)
    assert networks
    assert client_ip(_request("172.18.0.3", "203.0.113.9")) == "203.0.113.9"
    # ...but a request straight off the internet still cannot forge its address.
    assert client_ip(_request("203.0.113.9", "10.0.0.1")) == "203.0.113.9"
