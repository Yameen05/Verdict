"""Password reset (account recovery) and public-signup registration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "a-strong-test-password-123"
NEW_PASSWORD = "a-brand-new-password-456"


@pytest.fixture
def smtp_env(monkeypatch):
    """Pretend SMTP is configured and capture outbound mail instead of sending."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "verdict@example.com")
    get_settings.cache_clear()
    sent: list[dict] = []

    def fake_send(to: str, subject: str, body: str) -> bool:
        sent.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr("app.routers.password_reset.send_email", fake_send)
    yield sent
    get_settings.cache_clear()


def _extract_token(body: str) -> str:
    for line in body.splitlines():
        if "reset_token=" in line:
            return line.split("reset_token=", 1)[1].strip()
    raise AssertionError(f"no reset link in email body: {body!r}")


def test_status_reports_reset_and_signup_flags(client):
    status = client.get("/auth/status").json()
    assert status["public_signup_enabled"] is False
    assert status["password_reset_available"] is False  # no SMTP in tests


def test_request_returns_204_for_unknown_email(client, smtp_env):
    res = client.post(
        "/auth/password-reset/request", json={"email": "nobody@example.com"}
    )
    assert res.status_code == 204
    assert smtp_env == []  # nothing sent, same response as a real account


def test_request_without_smtp_is_silent_noop(client):
    res = client.post("/auth/password-reset/request", json={"email": OWNER_EMAIL})
    assert res.status_code == 204


def test_full_reset_flow(client, smtp_env):
    res = client.post("/auth/password-reset/request", json={"email": OWNER_EMAIL})
    assert res.status_code == 204
    assert len(smtp_env) == 1
    assert smtp_env[0]["to"] == OWNER_EMAIL
    token = _extract_token(smtp_env[0]["body"])

    # The owner's current session still works before confirmation.
    assert client.get("/auth/me").status_code == 200

    res = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "password": NEW_PASSWORD},
    )
    assert res.status_code == 204

    # All sessions are revoked...
    assert client.get("/auth/me").status_code == 401

    # ...the old password no longer works...
    from app.main import create_app

    with TestClient(create_app()) as fresh:
        old = fresh.post(
            "/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
        )
        assert old.status_code == 401

        # ...and the new one does.
        new = fresh.post(
            "/auth/login", json={"email": OWNER_EMAIL, "password": NEW_PASSWORD}
        )
        assert new.status_code == 200, new.text

    # The token is single-use.
    reuse = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "password": "yet-another-password-789"},
    )
    assert reuse.status_code == 401


def test_confirm_rejects_garbage_token(client):
    res = client.post(
        "/auth/password-reset/confirm",
        json={"token": "x" * 43, "password": NEW_PASSWORD},
    )
    assert res.status_code == 401


def test_confirm_rejects_weak_password(client, smtp_env):
    client.post("/auth/password-reset/request", json={"email": OWNER_EMAIL})
    token = _extract_token(smtp_env[0]["body"])
    # Contains the email's local part ("owner") — rejected by validate_password.
    res = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "password": "my-owner-password-123"},
    )
    assert res.status_code == 422


def test_public_signup_disabled_requires_invite(client):
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        res = visitor.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "a-strong-member-pass-123"},
        )
        assert res.status_code == 401


def test_public_signup_enabled_registers_without_invite(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", "true")
    get_settings.cache_clear()
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        assert visitor.get("/auth/status").json()["public_signup_enabled"] is True
        res = visitor.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "a-strong-member-pass-123"},
        )
        assert res.status_code == 201, res.text
        assert res.json()["user"]["role"] == "member"

        # Duplicate email still rejected.
        dup = visitor.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "a-strong-member-pass-123"},
        )
        assert dup.status_code == 409
    get_settings.cache_clear()


def test_public_signup_still_accepts_valid_invite(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", "true")
    get_settings.cache_clear()
    code = client.post("/auth/invites", json={"note": "vip"}).json()["code"]
    from app.main import create_app

    with TestClient(create_app()) as visitor:
        # A supplied code is still validated even with signup open.
        bad = visitor.post(
            "/auth/register",
            json={
                "invite_code": "not-a-real-code",
                "email": "a@example.com",
                "password": "a-strong-member-pass-123",
            },
        )
        assert bad.status_code == 401

        good = visitor.post(
            "/auth/register",
            json={
                "invite_code": code,
                "email": "b@example.com",
                "password": "a-strong-member-pass-123",
            },
        )
        assert good.status_code == 201
    get_settings.cache_clear()
