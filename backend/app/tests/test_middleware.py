"""Tests for request-ID and API-key middleware."""

from __future__ import annotations


def test_request_id_round_trip(client):
    res = client.get("/health", headers={"X-Request-ID": "trace-abc"})
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == "trace-abc"


def test_request_id_generated_when_missing(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("x-request-id")  # non-empty


def test_auth_disabled_by_default(client):
    res = client.get("/health")
    assert res.status_code == 200


def test_auth_required_when_key_set(monkeypatch):
    monkeypatch.setenv("VERDICT_API_KEY", "super-secret")
    from app.config import get_settings

    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        # Open paths still accessible
        assert c.get("/health").status_code == 200
        # Protected path requires header
        assert c.get("/research/history/AAPL").status_code == 401
        # With wrong key
        bad = c.get(
            "/research/history/AAPL", headers={"X-API-Key": "wrong"}
        )
        assert bad.status_code == 401
        # With correct key
        ok = c.get(
            "/research/history/AAPL", headers={"X-API-Key": "super-secret"}
        )
        assert ok.status_code == 200


def test_auth_rejection_preserves_request_id(monkeypatch):
    monkeypatch.setenv("VERDICT_API_KEY", "super-secret")
    from app.config import get_settings

    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        res = c.get("/research/history/AAPL", headers={"X-Request-ID": "trace-auth"})
        assert res.status_code == 401
        assert res.headers.get("x-request-id") == "trace-auth"
        assert res.json()["request_id"] == "trace-auth"


def test_error_envelope_includes_request_id(client):
    res = client.get("/research/history/!!!", headers={"X-Request-ID": "trace-xyz"})
    assert res.status_code == 400
    body = res.json()
    assert body["request_id"] == "trace-xyz"
    assert "detail" in body
