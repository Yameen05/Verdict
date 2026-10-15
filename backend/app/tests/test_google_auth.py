"""Google sign-in tests with locally signed JWTs and no calls to Google."""

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from google.auth import crypt, jwt
from google.auth.exceptions import TransportError
from sqlalchemy import select

from app.config import get_settings
from app.persistence.db import GoogleIdentity, GoogleLoginNonce, User, get_sessionmaker
from app.security import token_digest, utc_now

CLIENT_ID = "test-client.apps.googleusercontent.com"


@pytest.fixture
def google(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", "false")
    get_settings.cache_clear()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    signer = crypt.RSASigner.from_string(private, key_id="test-key")
    certs = json.dumps({"test-key": public}).encode()

    def transport(*args, **kwargs):
        return SimpleNamespace(status=200, data=certs)

    monkeypatch.setattr("app.services.google_sign_in.Request", lambda **kwargs: transport)

    def credential(nonce, /, **overrides):
        now = int(utc_now().timestamp())
        claims = {
            "iss": "https://accounts.google.com", "aud": CLIENT_ID,
            "iat": now, "exp": now + 3600, "sub": "google-subject",
            "email": "member@gmail.com", "email_verified": True, "nonce": nonce,
            **overrides,
        }
        return jwt.encode(signer, claims).decode()

    return credential


def _enable_signup(monkeypatch):
    monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", "true")
    get_settings.cache_clear()


def _login(visitor, google, *, invite_code="", **claims):
    nonce = visitor.get("/auth/google/nonce").json()["nonce"]
    return visitor.post("/auth/google", json={
        "credential": google(nonce, **claims), "invite_code": invite_code,
    })


def test_google_disabled_by_default(client):
    assert client.get("/auth/status").json()["google_client_id"] is None
    assert client.get("/auth/google/nonce").status_code == 503
    assert client.post("/auth/google", json={"credential": "anything"}).status_code == 503


def test_google_signup_and_session(client, google, monkeypatch):
    _enable_signup(monkeypatch)
    assert client.get("/auth/status").json()["google_client_id"] == CLIENT_ID
    with TestClient(client.app) as visitor:
        result = _login(visitor, google)
        assert result.status_code == 200, result.text
        assert result.json()["user"]["role"] == "member"
        assert result.json()["user"]["email"] == "member@gmail.com"
        assert "HttpOnly" in result.headers["set-cookie"]
        assert "SameSite=strict" in result.headers["set-cookie"]
        assert visitor.get("/auth/me").json() == result.json()
        assert visitor.post("/auth/logout").status_code == 403
        assert visitor.post("/auth/logout", headers={
            "X-CSRF-Token": result.json()["csrf_token"],
        }).status_code == 204
        assert visitor.get("/auth/me").status_code == 401
        assert visitor.post("/auth/login", json={
            "email": "member@gmail.com", "password": "",
        }).status_code != 200
        assert visitor.post("/auth/login", json={
            "email": "member@gmail.com",
            "password": "this-dummy-password-is-never-a-valid-account-password",
        }).status_code == 401


def test_google_invite_required_and_single_use(client, google):
    invite = client.post("/auth/invites", json={"note": "Google member"}).json()
    with TestClient(client.app) as visitor:
        assert _login(visitor, google).status_code == 401
        assert _login(visitor, google, invite_code="invalid").status_code == 401
        created = _login(visitor, google, invite_code=invite["code"])
        assert created.status_code == 200, created.text
        again = _login(visitor, google, invite_code=invite["code"],
                       sub="other-subject", email="another@gmail.com")
        assert again.status_code == 401
    listed = client.get("/auth/invites").json()["invites"]
    assert listed[0]["status"] == "used"


def test_google_existing_account_keeps_identity_after_email_change(client, google, monkeypatch):
    _enable_signup(monkeypatch)
    with TestClient(client.app) as visitor:
        created = _login(visitor, google).json()
        # Signup being closed never blocks an already linked account.
        monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", "false")
        get_settings.cache_clear()
        returned = _login(visitor, google, email="changed@gmail.com")
        assert returned.status_code == 200
        assert returned.json()["user"]["id"] == created["user"]["id"]


def test_google_links_existing_gmail_without_replacing_password(client, google, monkeypatch):
    _enable_signup(monkeypatch)
    with TestClient(client.app) as visitor:
        created = visitor.post("/auth/register", json={
            "email": "member@gmail.com", "password": "A-long-Password123",
        }).json()
        visitor.headers["X-CSRF-Token"] = created["csrf_token"]
        linked = _login(visitor, google)
        assert linked.status_code == 200, linked.text
        assert linked.json()["user"]["id"] == created["user"]["id"]
        assert visitor.post("/auth/login", json={
            "email": "member@gmail.com", "password": "A-long-Password123",
        }).status_code == 200
        # A different Google subject cannot claim this account through its email.
        assert _login(visitor, google, sub="another-subject").status_code == 409


def test_google_does_not_link_existing_third_party_email(client, google):
    with TestClient(client.app) as visitor:
        rejected = _login(visitor, google, email="owner@example.com")
        assert rejected.status_code == 409
        # Hosted-domain claims alone cannot link an existing password account.
        unlinked = _login(visitor, google, email="owner@example.com", hd="example.com")
        assert unlinked.status_code == 409
        visitor.cookies.update(client.cookies)
        visitor.headers["X-CSRF-Token"] = client.headers["X-CSRF-Token"]
        accepted = _login(visitor, google, email="owner@example.com", hd="example.com")
        assert accepted.status_code == 200
        assert accepted.json()["user"]["role"] == "owner"


@pytest.mark.parametrize("claims", [
    {"aud": "another-client"}, {"iss": "https://attacker.example"},
    {"exp": 1}, {"email_verified": False}, {"sub": ""},
    {"nonce": "another-browser"},
])
def test_google_rejects_invalid_claims(client, google, monkeypatch, claims):
    _enable_signup(monkeypatch)
    with TestClient(client.app) as visitor:
        assert _login(visitor, google, **claims).status_code in {401, 403}
        assert visitor.get("/auth/me").status_code == 401


def test_google_rejects_tampered_signature_and_replay(client, google, monkeypatch):
    _enable_signup(monkeypatch)
    with TestClient(client.app) as visitor:
        nonce = visitor.get("/auth/google/nonce").json()["nonce"]
        token = google(nonce)
        parts = token.split(".")
        parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
        assert visitor.post("/auth/google", json={"credential": ".".join(parts)}).status_code == 401
        assert visitor.post("/auth/google", json={"credential": token}).status_code == 403
        nonce = visitor.get("/auth/google/nonce").json()["nonce"]
        raw_cookie = visitor.cookies.get("verdict_google_nonce")
        body = {"credential": google(nonce)}
        assert visitor.post("/auth/google", json=body).status_code == 200
        visitor.cookies.set("verdict_google_nonce", raw_cookie)
        assert visitor.post("/auth/google", json=body).status_code == 403


def test_google_rejects_missing_and_wrong_browser_cookie(client, google, monkeypatch):
    _enable_signup(monkeypatch)
    with TestClient(client.app) as visitor:
        nonce = visitor.get("/auth/google/nonce").json()["nonce"]
        visitor.cookies.clear()
        assert visitor.post("/auth/google", json={"credential": google(nonce)}).status_code == 403
        visitor.cookies.set("verdict_google_nonce", "wrong-browser")
        assert visitor.post("/auth/google", json={"credential": google(nonce)}).status_code == 403


async def test_google_expired_nonce(client, google, monkeypatch):
    _enable_signup(monkeypatch)
    with TestClient(client.app) as visitor:
        nonce = visitor.get("/auth/google/nonce").json()["nonce"]
        async with get_sessionmaker()() as db:
            row = await db.get(GoogleLoginNonce, nonce)
            row.expires_at = utc_now() - timedelta(seconds=1)
            await db.commit()
        assert visitor.post("/auth/google", json={"credential": google(nonce)}).status_code == 403


async def test_google_inactive_account_cannot_sign_in(client, google, monkeypatch):
    _enable_signup(monkeypatch)
    with TestClient(client.app) as visitor:
        assert _login(visitor, google).status_code == 200
        async with get_sessionmaker()() as db:
            identity = await db.get(GoogleIdentity, "google-subject")
            user = await db.get(User, identity.user_id)
            user.is_active = False
            await db.commit()
        visitor.cookies.clear()
        assert _login(visitor, google).status_code == 401
        assert visitor.get("/auth/me").status_code == 401


async def test_google_new_nonce_retires_previous_challenge(client, google):
    first = client.get("/auth/google/nonce")
    assert first.headers["cache-control"] == "no-store"
    assert first.json()["nonce"] == token_digest(client.cookies.get("verdict_google_nonce"))
    second = client.get("/auth/google/nonce").json()["nonce"]
    async with get_sessionmaker()() as db:
        assert await db.get(GoogleLoginNonce, first.json()["nonce"]) is None
        assert await db.get(GoogleLoginNonce, second) is not None
        assert (await db.scalars(select(User))).all()  # Owner account is unchanged.


def test_google_provider_outage_returns_retryable_error(client, google, monkeypatch):
    async def unavailable(*args):
        raise TransportError("Certificate service unavailable")

    monkeypatch.setattr("app.routers.google_auth.verify_google_credential", unavailable)
    with TestClient(client.app) as visitor:
        assert _login(visitor, google).status_code == 503
        assert visitor.get("/auth/me").status_code == 401


def test_google_nonce_cookie_is_secure_in_production(client, google, monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    get_settings.cache_clear()
    with TestClient(client.app, base_url="https://testserver") as visitor:
        result = visitor.get("/auth/google/nonce")
        assert result.status_code == 200
        assert "__Host-verdict_google_nonce=" in result.headers["set-cookie"]
        assert "Secure" in result.headers["set-cookie"]
        assert "HttpOnly" in result.headers["set-cookie"]
        assert "Path=/" in result.headers["set-cookie"]


def test_google_rejects_cross_origin_login(client, google):
    nonce = client.get("/auth/google/nonce").json()["nonce"]
    result = client.post("/auth/google", headers={"Origin": "https://attacker.example"},
                         json={"credential": google(nonce)})
    assert result.status_code == 403


def test_google_cannot_attach_to_a_pre_registered_password_account(client, google, monkeypatch):
    _enable_signup(monkeypatch)
    with TestClient(client.app) as attacker:
        assert attacker.post("/auth/register", json={
            "email": "member@gmail.com", "password": "A-long-attacker-password-123",
        }).status_code == 201
    with TestClient(client.app) as actual_email_owner:
        assert _login(actual_email_owner, google).status_code == 409
