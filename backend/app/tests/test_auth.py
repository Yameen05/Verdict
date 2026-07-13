"""End-to-end owner authentication and two-factor tests."""

from __future__ import annotations

import pyotp
from fastapi.testclient import TestClient

from app.config import get_settings

BOOTSTRAP_TOKEN = "test-bootstrap-token-with-at-least-32-characters"
OWNER = {
    "email": "owner@example.com",
    "password": "a-strong-test-password-123",
}


def _new_client(monkeypatch, *, require_2fa: bool) -> TestClient:
    monkeypatch.setenv("REQUIRE_2FA", str(require_2fa).lower())
    get_settings.cache_clear()
    from app.main import create_app

    return TestClient(create_app())


def test_bootstrap_is_one_time_and_requires_server_token(monkeypatch):
    with _new_client(monkeypatch, require_2fa=False) as client:
        assert client.get("/auth/status").json()["bootstrap_required"] is True
        rejected = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": "wrong"},
            json=OWNER,
        )
        assert rejected.status_code == 404

        created = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json=OWNER,
        )
        assert created.status_code == 201
        assert created.json()["user"]["email"] == OWNER["email"]
        assert created.cookies.get("verdict_session")
        assert client.get("/auth/status").json()["bootstrap_required"] is False

        duplicate = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json={"email": "other@example.com", "password": "another-strong-password-123"},
        )
        assert duplicate.status_code == 404


def test_mandatory_totp_recovery_and_logout(monkeypatch):
    with _new_client(monkeypatch, require_2fa=True) as client:
        created = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json=OWNER,
        )
        assert created.status_code == 201
        csrf = created.json()["csrf_token"]
        assert created.json()["requires_2fa_setup"] is True
        assert client.get("/research/history/AAPL").status_code == 403

        setup = client.post("/auth/2fa/setup", headers={"X-CSRF-Token": csrf})
        assert setup.status_code == 200
        assert setup.json()["qr_code_data_uri"].startswith("data:image/svg+xml;base64,")

        code = pyotp.TOTP(setup.json()["secret"]).now()
        enabled = client.post(
            "/auth/2fa/enable",
            headers={"X-CSRF-Token": csrf},
            json={"code": code},
        )
        assert enabled.status_code == 200
        recovery_codes = enabled.json()["recovery_codes"]
        assert len(recovery_codes) == 10
        assert client.get("/research/history/AAPL").status_code == 200

        csrf = enabled.json()["csrf_token"]
        assert client.post("/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
        login = client.post("/auth/login", json=OWNER)
        assert login.status_code == 200
        assert login.json()["requires_2fa"] is True

        recovered = client.post(
            "/auth/2fa/verify",
            json={
                "challenge_token": login.json()["challenge_token"],
                "code": recovery_codes[0],
            },
        )
        assert recovered.status_code == 200

        csrf = recovered.json()["csrf_token"]
        client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
        second_login = client.post("/auth/login", json=OWNER).json()
        reused = client.post(
            "/auth/2fa/verify",
            json={
                "challenge_token": second_login["challenge_token"],
                "code": recovery_codes[0],
            },
        )
        assert reused.status_code == 401


def test_state_changing_route_rejects_missing_csrf(monkeypatch):
    with _new_client(monkeypatch, require_2fa=False) as client:
        created = client.post(
            "/auth/bootstrap",
            headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            json=OWNER,
        )
        assert created.status_code == 201
        blocked = client.post("/research/AAPL")
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "CSRF validation failed"


def test_validation_errors_do_not_reflect_credentials(monkeypatch):
    with _new_client(monkeypatch, require_2fa=False) as client:
        secret = "this-value-must-never-be-reflected"
        response = client.post(
            "/auth/login",
            json={"email": "not-an-email", "password": secret * 8},
        )

        assert response.status_code == 422
        assert secret not in response.text
