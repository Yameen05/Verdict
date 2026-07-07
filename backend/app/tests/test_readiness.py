"""Tests for the /health/ready endpoint."""

from __future__ import annotations

from app.routers import health as health_mod


async def test_ready_reports_degraded_with_no_keys(client):
    res = client.get("/health/ready")
    # LLM check fails with no key → 503; local vectorstore is fine keyless.
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert set(body["checks"].keys()) == {"llm", "newsapi", "vectorstore"}
    # newsapi without key is "ok skipped" (optional dep)
    assert body["checks"]["newsapi"]["ok"] is True
    # local vector backend needs no key — reports ok with a chunk count
    assert body["checks"]["vectorstore"]["ok"] is True
    assert "local" in body["checks"]["vectorstore"]["detail"]


async def test_ready_reports_ready_when_all_ok(client, monkeypatch):
    async def ok_llm():
        return True, "reachable"

    async def ok_vectorstore():
        return True, "local (12 chunks indexed)"

    async def ok_news():
        return True, "reachable"

    monkeypatch.setattr(health_mod, "_check_llm", ok_llm)
    monkeypatch.setattr(health_mod, "_check_vectorstore", ok_vectorstore)
    monkeypatch.setattr(health_mod, "_check_newsapi", ok_news)

    res = client.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert all(v["ok"] for v in body["checks"].values())
