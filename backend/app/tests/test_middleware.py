"""Tests for request IDs, authentication enforcement, and secure headers."""

from __future__ import annotations


def test_request_id_round_trip(client):
    res = client.get("/health", headers={"X-Request-ID": "trace-abc"})
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == "trace-abc"


def test_request_id_generated_when_missing(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("x-request-id")  # non-empty


def test_protected_route_requires_session():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/research/history/AAPL").status_code == 401


def test_auth_rejection_preserves_request_id():
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


def test_security_headers_are_present(client):
    res = client.get("/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["cache-control"] == "no-store"
