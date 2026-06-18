"""Shared test fixtures.

Every test runs against an isolated in-memory SQLite DB; the Verdict API key
defaults to unset (auth disabled) unless a test opts in via monkeypatch.
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
    monkeypatch.setenv("VERDICT_API_KEY", "")
    # Isolate the suite from a developer's real key. Local runs put the OpenAI
    # key in backend/.env, which pytest (run from backend/) would otherwise load
    # and then make live API calls (e.g. the readiness probe's models.list()).
    monkeypatch.setenv("OPENAI_API_KEY", "")
    # Also isolate from a dev's LLM provider config in backend/.env (e.g. a
    # Gemini base URL), so tests run deterministically against OpenAI defaults.
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("RATE_LIMIT_RESEARCH", "1000/minute")
    monkeypatch.setenv("RATE_LIMIT_FILINGS", "1000/minute")
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
    """A TestClient that runs the app's lifespan (so the DB is created)."""
    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
