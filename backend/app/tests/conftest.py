"""Shared test fixtures.

Every test runs against an isolated database and deterministic auth settings.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch, tmp_path):
    """Reset settings + point DB at a temp file per-test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "vectors.db"))
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ALLOWED_HOSTS", "testserver,localhost")
    monkeypatch.setenv("AUTH_BOOTSTRAP_TOKEN", "test-bootstrap-token-with-at-least-32-characters")
    monkeypatch.setenv(
        "AUTH_ENCRYPTION_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("REQUIRE_2FA", "false")
    # Isolate the suite from a developer's real key. Local runs put the OpenAI
    # key in backend/.env, which pytest (run from backend/) would otherwise load
    # and then make live API calls (e.g. the readiness probe's models.list()).
    monkeypatch.setenv("OPENAI_API_KEY", "")
    # Also isolate from a dev's LLM provider config in backend/.env (e.g. a
    # Gemini base URL), so tests run deterministically against OpenAI defaults.
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("STOCKTWITS_ENABLED", "false")
    monkeypatch.setenv("REDDIT_ENABLED", "false")
    monkeypatch.setenv("RATE_LIMIT_RESEARCH", "1000/minute")
    monkeypatch.setenv("RATE_LIMIT_FILINGS", "1000/minute")
    monkeypatch.setenv("RATE_LIMIT_AUTH", "1000/minute")
    get_settings.cache_clear()
    # Reset persistence singletons so the new URL is picked up.
    from app.persistence import db as db_mod

    db_mod._engine = None
    db_mod._sessionmaker = None
    yield
    get_settings.cache_clear()
    db_mod._engine = None
    db_mod._sessionmaker = None


@pytest.fixture
def client():
    """Authenticated TestClient used by existing protected-route tests."""
    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        created = c.post(
            "/auth/bootstrap",
            headers={
                "X-Bootstrap-Token": "test-bootstrap-token-with-at-least-32-characters"
            },
            json={
                "email": "owner@example.com",
                "password": "a-strong-test-password-123",
            },
        )
        assert created.status_code == 201, created.text
        c.headers.update({"X-CSRF-Token": created.json()["csrf_token"]})
        yield c
