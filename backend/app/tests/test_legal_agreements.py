"""Agreement evidence, rejected signup, and pre-agreement database compatibility."""
import hashlib
import json
from datetime import UTC
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.main import create_app
from app.persistence.agreements import LegalAcceptanceRecord
from app.persistence.db import AuditEvent, User, get_engine, get_sessionmaker, init_db
from app.security import utc_now
from app.services.legal_agreements import LEGAL_MANIFEST, current_legal_acceptance

TOKEN = "test-bootstrap-token-with-at-least-32-characters"
ACCOUNT = {"email": "new@example.com", "password": "A-strong-test-password-123"}


def invalid_acceptance(case):
    if case == "omitted":
        return {}
    acceptance = current_legal_acceptance()
    acceptance[{"false": "accepted", "stale_terms": "terms_version", "stale_risk": "risk_version",
                "stale_privacy": "privacy_version", "stale_content": "content_sha256"}[case]] = (
                    False if case == "false" else "old")
    return {"legal_acceptance": acceptance}


CASES = ["omitted", "false", "stale_terms", "stale_risk", "stale_privacy", "stale_content"]


@pytest.mark.parametrize("case", CASES)
def test_bootstrap_rejects_missing_false_and_stale_agreement(case):
    with TestClient(create_app()) as visitor:
        result = visitor.post("/auth/bootstrap", json={**ACCOUNT, **invalid_acceptance(case)},
                              headers={"X-Bootstrap-Token": TOKEN})
        assert result.status_code == 428
        assert visitor.get("/auth/status").json()["bootstrap_required"] is True
        assert visitor.get("/auth/me").status_code == 401
        async def empty():
            async with get_sessionmaker()() as db:
                assert await db.scalar(select(func.count()).select_from(User)) == 0
                assert await db.scalar(select(func.count()).select_from(LegalAcceptanceRecord)) == 0
        visitor.portal.call(empty)


@pytest.mark.parametrize("mode", ["public", "invite"])
@pytest.mark.parametrize("case", CASES)
def test_email_signup_rejects_missing_false_and_stale_agreement(client, monkeypatch, mode, case):
    invite = client.post("/auth/invites", json={"note": "agreement test"}).json()
    monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", str(mode == "public").lower())
    get_settings.cache_clear()
    with TestClient(client.app) as visitor:
        payload = {**ACCOUNT, **invalid_acceptance(case)}
        if mode == "invite":
            payload["invite_code"] = invite["code"]
        assert visitor.post("/auth/register", json=payload).status_code == 428
        assert visitor.get("/auth/me").status_code == 401
    assert client.get("/auth/invites").json()["invites"][0]["status"] == "pending"
    async def no_member():
        async with get_sessionmaker()() as db:
            assert await db.scalar(select(User).where(User.email == ACCOUNT["email"])) is None
            assert await db.scalar(select(func.count()).select_from(LegalAcceptanceRecord)) == 1
    client.portal.call(no_member)


@pytest.mark.parametrize("mode", ["bootstrap", "public", "invite"])
def test_accepted_signup_persists_versions_server_time_and_audit(client, monkeypatch, mode):
    # The fixture owner's bootstrap also creates a verifiable agreement record.
    started = utc_now()
    if mode == "bootstrap":
        user_id = client.get("/auth/me").json()["user"]["id"]
        started = started.replace(year=2000)
    else:
        monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", str(mode == "public").lower())
        get_settings.cache_clear()
        payload = {**ACCOUNT, "legal_acceptance": current_legal_acceptance()}
        if mode == "invite":
            payload["invite_code"] = client.post("/auth/invites", json={"note": "agree"}).json()["code"]
        with TestClient(client.app) as visitor:
            result = visitor.post("/auth/register", json=payload)
            assert result.status_code == 201, result.text
            user_id = result.json()["user"]["id"]
    ended = utc_now()
    async def inspect_record():
        async with get_sessionmaker()() as db:
            row = await db.get(LegalAcceptanceRecord, user_id)
            assert row is not None
            for key, version in LEGAL_MANIFEST["versions"].items():
                assert getattr(row, f"{key}_version") == version
            assert row.content_sha256 == LEGAL_MANIFEST["content_sha256"]
            assert row.purpose == "account_creation"
            assert started <= row.accepted_at.replace(tzinfo=UTC) <= ended
            audit = await db.scalar(select(AuditEvent).where(AuditEvent.user_id == user_id,
                                  AuditEvent.event == "account_legal_agreement"))
            assert audit.details["content_sha256"] == row.content_sha256
    client.portal.call(inspect_record)


def test_client_cannot_supply_acceptance_timestamp(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_SIGNUP_ENABLED", "true")
    get_settings.cache_clear()
    acceptance = {**current_legal_acceptance(), "accepted_at": "2000-01-01T00:00:00Z"}
    with TestClient(client.app) as visitor:
        assert visitor.post("/auth/register", json={**ACCOUNT, "legal_acceptance": acceptance}).status_code == 422


def test_existing_database_migration_does_not_invent_agreement(client):
    async def migrate():
        async with get_sessionmaker()() as db:
            user = await db.scalar(select(User))
            original = (user.id, user.password_hash, user.created_at)
        async with get_engine().begin() as conn:
            await conn.run_sync(LegalAcceptanceRecord.__table__.drop)
        await init_db()
        await init_db()
        async with get_sessionmaker()() as db:
            assert await db.scalar(select(func.count()).select_from(LegalAcceptanceRecord)) == 0
            user = await db.get(User, original[0])
            assert (user.id, user.password_hash, user.created_at) == original
    client.portal.call(migrate)
    assert client.get("/auth/me").status_code == 200
    with TestClient(client.app) as visitor:
        assert visitor.post("/auth/login", json={"email": "owner@example.com",
                     "password": "A-strong-test-password-123"}).status_code == 200
    async def still_empty():
        async with get_sessionmaker()() as db:
            assert await db.scalar(select(func.count()).select_from(LegalAcceptanceRecord)) == 0
    client.portal.call(still_empty)


def test_manifest_matches_presented_documents(client):
    root = Path(__file__).resolve().parents[3]
    assert json.loads((root / "frontend/src/lib/legalManifest.json").read_text()) == LEGAL_MANIFEST
    assert hashlib.sha256((root / "frontend/src/lib/legal.ts").read_bytes()).hexdigest() == LEGAL_MANIFEST["content_sha256"]
    assert client.get("/auth/status").json()["legal_manifest"] == LEGAL_MANIFEST
