"""End-to-end password authentication and legacy-account compatibility tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.persistence.db import User, UserSession, get_sessionmaker
from app.services.legal_agreements import current_legal_acceptance

BOOTSTRAP_TOKEN = "test-bootstrap-token-with-at-least-32-characters"
OWNER = {
    "email": "owner@example.com",
    "password": "A-strong-test-password-123",
}


def _new_client() -> TestClient:
    get_settings.cache_clear()
    from app.main import create_app

    return TestClient(create_app())


def test_bootstrap_is_one_time_and_requires_server_token(monkeypatch):
    with _new_client() as client:
        assert client.get("/auth/status").json()["bootstrap_required"] is True
        rejected = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": "wrong"},
            json=dict(OWNER, legal_acceptance=current_legal_acceptance()),
        )
        assert rejected.status_code == 404

        created = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json=dict(OWNER, legal_acceptance=current_legal_acceptance()),
        )
        assert created.status_code == 201
        assert created.json()["user"]["email"] == OWNER["email"]
        assert created.cookies.get("verdict_session")
        assert client.get("/auth/status").json()["bootstrap_required"] is False

        duplicate = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json=dict({"email": "other@example.com", "password": "Another-strong-password-123"}, legal_acceptance=current_legal_acceptance()),
        )
        assert duplicate.status_code == 404


@pytest.mark.parametrize("previously_enrolled", [False, True])
def test_password_login_for_legacy_accounts(monkeypatch, previously_enrolled):
    # Old deployment settings must not restore the removed requirement.
    monkeypatch.setenv("REQUIRE_2FA", "true")
    with _new_client() as client:
        created = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json=dict(OWNER, legal_acceptance=current_legal_acceptance()),
        )
        assert created.status_code == 201
        assert "requires_2fa_setup" not in created.json()
        csrf = created.json()["csrf_token"]

        async def restore_legacy_state():
            async with get_sessionmaker()() as db:
                user = await db.scalar(select(User))
                user.totp_enabled = previously_enrolled
                user.totp_secret_encrypted = "legacy-secret-with-no-decryption-key"
                session = await db.scalar(select(UserSession))
                session.mfa_verified = False
                await db.commit()

        client.portal.call(restore_legacy_state)
        assert client.get("/auth/me").status_code == 200
        assert client.get("/research/history/AAPL").status_code == 200
        assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
        assert client.get("/research/history/AAPL").status_code == 401

        rejected = client.post("/auth/login", json={**OWNER, "password": "wrong"})
        assert rejected.status_code == 401
        assert client.get("/research/history/AAPL").status_code == 401

        login = client.post("/auth/login", json=OWNER)
        assert login.status_code == 200
        assert login.cookies.get("verdict_session")
        assert "challenge_token" not in login.json()
        assert "requires_2fa_setup" not in login.json()
        assert "two_factor_enabled" not in login.json()["user"]
        assert client.get("/research/history/AAPL").status_code == 200
        assert client.post("/auth/logout").status_code == 403
        assert client.post(
            "/auth/logout", headers={"X-CSRF-Token": login.json()["csrf_token"]}
        ).status_code == 204


@pytest.mark.parametrize("route", ["setup", "enable", "verify"])
def test_two_factor_endpoints_removed(client, route):
    assert client.post(f"/auth/2fa/{route}", json={}).status_code == 404


def test_state_changing_route_rejects_missing_csrf(monkeypatch):
    with _new_client() as client:
        created = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json=dict(OWNER, legal_acceptance=current_legal_acceptance()),
        )
        assert created.status_code == 201
        blocked = client.post("/research/AAPL")
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "CSRF validation failed"


def test_validation_errors_do_not_reflect_credentials(monkeypatch):
    with _new_client() as client:
        secret = "this-value-must-never-be-reflected"
        response = client.post(
            "/auth/login",
            json={"email": "not-an-email", "password": secret * 8},
        )

        assert response.status_code == 422
        assert secret not in response.text
