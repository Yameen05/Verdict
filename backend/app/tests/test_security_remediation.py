"""Regression tests for the October security audit's exploitable boundaries."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app.config import Settings, get_settings
from app.main import create_app
from app.observability.logging import JSONFormatter
from app.persistence.db import PasswordResetToken, User, get_sessionmaker
from app.resource_limits import ResourceLimitsMiddleware
from app.security import token_digest
from app.services.budgets import reserve_provider_operation

SECURE = dict(environment="production", session_cookie_secure=True, docs_enabled=False,
              cors_origins="https://verdict.example.com", allowed_hosts="verdict.example.com",
              auth_bootstrap_token="a" * 48)


@pytest.mark.parametrize("override", [
    {"cors_origins": "http://verdict.example.com"}, {"cors_origins": ""},
    {"cors_origins": "https://verdict.example.com/path"},
    {"cors_origins": "https://user:secret@verdict.example.com"},
    {"allowed_hosts": "*.example.com"}, {"trusted_proxy_ips": "1.2.3.4/0"},
    {"trusted_proxy_ips": "broken"}, {"llm_base_url": "http://provider.example/v1"},
    {"smtp_host": "smtp.example.com"},
    {"smtp_host": "smtp.example.com", "smtp_from": "mail@example.com",
     "app_public_url": "https://verdict.example.com", "smtp_starttls": False},
    {"app_public_url": "https://attacker.example"},
])
def test_production_rejects_unsafe_configuration(override):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **(SECURE | override))


def test_signup_cannot_lock_out_first_owner(monkeypatch):
    monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", "true")
    get_settings.cache_clear()
    with TestClient(create_app()) as visitor:
        res = visitor.post("/auth/register", json={
            "email": "member@example.com", "password": "A-new-long-password-123",
        })
        assert res.status_code == 403
        assert visitor.get("/auth/status").json()["bootstrap_required"] is True


async def test_daily_admission_is_atomic_and_failed_work_stays_charged(client, monkeypatch):
    monkeypatch.setenv("DAILY_RUNS_GLOBAL", "2")
    get_settings.cache_clear()
    uid = client.get("/auth/me").json()["user"]["id"]
    results = await asyncio.gather(*(reserve_provider_operation(uid) for _ in range(8)),
                                   return_exceptions=True)
    assert sum(r is None for r in results) == 2
    assert all(r is None or isinstance(r, HTTPException) and r.status_code == 429 for r in results)
    with pytest.raises(HTTPException) as err:
        await reserve_provider_operation(uid)
    assert err.value.status_code == 429


async def test_personal_rejection_does_not_consume_global_budget(client, monkeypatch):
    from app.services.budgets import AdmissionCounter
    monkeypatch.setenv("DAILY_RUNS_PER_USER", "1")
    get_settings.cache_clear()
    uid = client.get("/auth/me").json()["user"]["id"]
    await reserve_provider_operation(uid)
    with pytest.raises(HTTPException):
        await reserve_provider_operation(uid)
    async with get_sessionmaker()() as db:
        global_counter = await db.scalar(select(AdmissionCounter).where(
            AdmissionCounter.key.like("%:global")))
        assert global_counter.used == 1


async def test_concurrent_reset_consumes_token_once(client, monkeypatch):
    from datetime import timedelta

    from app.security import new_token, utc_now
    raw = new_token()
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User).where(User.role == "owner"))
        db.add(PasswordResetToken(token_hash=token_digest(raw), user_id=user.id,
                                 expires_at=utc_now() + timedelta(minutes=10)))
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),
                                base_url="http://testserver") as c:
        responses = await asyncio.gather(*(c.post("/auth/password-reset/confirm", json={
            "token": raw, "password": f"A-new-long-password-{i}123",
        }) for i in range(2)))
    assert sorted(r.status_code for r in responses) == [204, 401]


async def test_concurrent_invite_has_only_one_member(client):
    code = client.post("/auth/invites", json={"note": "race"}).json()["code"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),
                                base_url="http://testserver") as c:
        responses = await asyncio.gather(*(c.post("/auth/register", json={
            "invite_code": code, "email": f"member{i}@example.com",
            "password": "A-member-long-password-123",
        }) for i in range(2)))
    assert sorted(r.status_code for r in responses) == [201, 401]
    async with get_sessionmaker()() as db:
        assert len((await db.scalars(select(User))).all()) == 2


def test_login_account_limit_survives_different_client_ips(client):
    for i in range(10):
        res = client.post("/auth/login", headers={"X-Forwarded-For": f"203.0.113.{i}"},
                          json={"email": "owner@example.com", "password": "wrong"})
        assert res.status_code == 401
    assert client.post("/auth/login", json={
        "email": "OWNER@example.com", "password": "A-strong-test-password-123",
    }).status_code == 429


def test_error_headers_and_fetch_site_rejection(client):
    res = client.post("/auth/login", headers={"Sec-Fetch-Site": "cross-site"}, json={})
    assert res.status_code == 403
    assert res.headers["cache-control"] == "no-store"
    assert client.get("/health", headers={"Host": "evil.example"}).headers["x-frame-options"] == "DENY"


def test_logger_hides_configured_keys_and_exception_values(monkeypatch):
    secret = "secret-provider-key-123456789"
    monkeypatch.setenv("NEWS_API_KEY", secret)
    get_settings.cache_clear()
    try:
        raise ValueError("sensitive-user-password")
    except ValueError:
        import sys
        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "upstream_failed", (),
                                   sys.exc_info())
    record.reason = f"https://example.com?apiKey={secret}&token=abcsecret"
    formatted = JSONFormatter().format(record)
    assert secret not in formatted
    assert "abcsecret" not in formatted
    assert "sensitive-user-password" not in formatted
    assert json.loads(formatted)["error_type"] == "ValueError"


async def test_asgi_rejects_chunked_oversize_before_parser(monkeypatch):
    import app.resource_limits as module
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(
        max_request_bytes=8, max_concurrent_requests=1, request_timeout_seconds=1))
    downstream = AsyncMock()
    middleware = ResourceLimitsMiddleware(downstream)
    chunks = iter([{"type": "http.request", "body": b"12345", "more_body": True},
                   {"type": "http.request", "body": b"67890", "more_body": False}])
    async def receive():
        return next(chunks)
    send = AsyncMock()
    await middleware({"type": "http", "path": "/filings/ingest"}, receive, send)
    assert send.call_args_list[0].args[0]["status"] == 413
    downstream.assert_not_called()
    assert middleware.active == 0


async def test_busy_deadline_releases_capacity(monkeypatch):
    import app.resource_limits as module
    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(
        max_request_bytes=8, max_concurrent_requests=1, request_timeout_seconds=.02))
    entered = asyncio.Event()
    async def slow(scope, receive, send):
        entered.set()
        await asyncio.sleep(5)
    middleware = ResourceLimitsMiddleware(slow)
    receive = AsyncMock(return_value={"type": "http.request", "body": b""})
    send1, send2 = AsyncMock(), AsyncMock()
    first = asyncio.create_task(middleware({"type": "http", "path": "/market/AAPL/history"}, receive, send1))
    await entered.wait()
    await middleware({"type": "http", "path": "/market/MSFT/history"}, receive, send2)
    assert send2.call_args_list[0].args[0]["status"] == 503
    await first
    assert send1.call_args_list[0].args[0]["status"] == 504
    assert middleware.active == 0


async def test_watchlist_cap_is_atomic_across_concurrent_writes(client):
    from app.persistence.user_state import WatchlistItem
    uid = client.get("/auth/me").json()["user"]["id"]
    async with get_sessionmaker()() as db:
        db.add_all(WatchlistItem(user_id=uid, ticker=f"STOCK{i}") for i in range(23))
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()),
                                base_url="http://testserver", cookies=dict(client.cookies),
                                headers={"X-CSRF-Token": client.headers["X-CSRF-Token"]}) as c:
        responses = await asyncio.gather(*(c.post("/me/watchlist", json={"ticker": t})
                                          for t in ("EXTRA1", "EXTRA2")))
        assert sorted(r.status_code for r in responses) == [200, 400]
        assert len((await c.get("/me/watchlist")).json()["tickers"]) == 24


async def test_new_policy_keeps_legacy_password_login(client):
    from app.security import hash_password
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User).where(User.role == "owner"))
        user.password_hash = hash_password("Old123")
        await db.commit()
    assert client.post("/auth/login", json={"email": "owner@example.com", "password": "Old123"}).status_code == 200


def test_nonfinite_position_price_is_rejected(client):
    result = client.post("/me/positions", content='{"ticker":"AAPL","amount_usd":100,"buy_date":"2026-10-15","buy_price":1e999}',
                         headers={"Content-Type": "application/json"})
    assert result.status_code == 422
    assert client.get("/me/positions/AAPL").json()["position"] is None


def test_nonascii_csrf_is_a_rejection_not_an_internal_error():
    from starlette.requests import Request

    from app.security import verify_csrf
    req = Request({"type": "http", "method": "POST", "headers": [(b"x-csrf-token", b"\xff")]})
    with pytest.raises(HTTPException) as err:
        verify_csrf(req, SimpleNamespace(session=SimpleNamespace(csrf_token="ascii-token")))
    assert err.value.status_code == 403


def test_startup_validation_does_not_dump_secret_configuration():
    key = "startup-sensitive-key-value-12345"
    with pytest.raises(ValidationError) as err:
        Settings(_env_file=None, environment="production", llm_api_key=key)
    assert key not in str(err.value)


def test_cors_origins_canonicalize_trailing_slash():
    settings = Settings(_env_file=None, **(SECURE | {"cors_origins": "https://verdict.example.com/", "app_public_url": "https://verdict.example.com/"}))
    assert settings.cors_origins_list == ["https://verdict.example.com"]
