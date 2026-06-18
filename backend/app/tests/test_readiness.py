"""Tests for the /health/ready endpoint."""

from __future__ import annotations

from app.routers import health as health_mod


async def test_ready_reports_degraded_with_no_keys(client):
    res = client.get("/health/ready")
    # All deps degraded since no keys → 503
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert set(body["checks"].keys()) == {"llm", "newsapi", "pinecone"}
    # newsapi without key is "ok skipped" (optional dep)
    assert body["checks"]["newsapi"]["ok"] is True


async def test_ready_reports_ready_when_all_ok(client, monkeypatch):
    async def ok_llm():
        return True, "reachable"

    async def ok_pinecone():
        return True, "reachable (0 indexes)"

    async def ok_news():
        return True, "reachable"

    monkeypatch.setattr(health_mod, "_check_llm", ok_llm)
    monkeypatch.setattr(health_mod, "_check_pinecone", ok_pinecone)
    monkeypatch.setattr(health_mod, "_check_newsapi", ok_news)

    res = client.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert all(v["ok"] for v in body["checks"].values())
