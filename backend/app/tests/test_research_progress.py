"""Fixture stream coverage: no model calls, external APIs, or persistent writes."""

import json

import httpx
import pytest
from openai import APIStatusError

from app.observability.cost import start_tracking
from app.routers import research as research_mod
from app.schemas.research import ResearchReport


@pytest.mark.parametrize("failure", [None, "busy", "timeout"])
async def test_sse_routes_real_progress_and_normalizes_terminal_errors(monkeypatch, failure):
    class Graph:
        async def astream(self, *_args, **_kwargs):
            yield (
                "custom",
                {"kind": "provider_wait", "id": "fixture", "reason": "queue", "phase": "started"},
            )
            yield "custom", {"kind": "filing_question", "index": 2}
            yield (
                "custom",
                {"kind": "provider_wait", "id": "fixture", "reason": "queue", "phase": "done"},
            )
            yield "custom", {"kind": "judge_phase", "phase": "deliberating"}
            if failure == "busy":
                raise APIStatusError(
                    "PRIVATE",
                    response=httpx.Response(
                        503, request=httpx.Request("POST", "https://example.test")
                    ),
                    body={},
                )
            if failure == "timeout":
                raise TimeoutError("PRIVATE")
            yield (
                "updates",
                {
                    "judge": {
                        "report": ResearchReport(
                            ticker="AAPL",
                            recommendation="Hold",
                            justification="fixture",
                            company_overview="",
                            financial_health="",
                        )
                    }
                },
            )

    async def no_sessions():
        if False:
            yield None

    monkeypatch.setattr(research_mod, "get_graph", lambda: Graph())
    monkeypatch.setattr(research_mod, "session_scope", no_sessions)
    events = [
        event
        async for event in research_mod._sse_stream(
            "AAPL", start_tracking(), "fixture", 1, None, 14, False
        )
    ]
    assert [event["event"] for event in events[:5]] == [
        "started",
        "progress",
        "progress",
        "progress",
        "debate",
    ]
    last = json.loads(events[-1]["data"])
    assert "PRIVATE" not in str(events)
    if failure:
        assert events[-1]["event"] == "error"
        assert last["failure"]["kind"] == ("provider_busy" if failure == "busy" else "timeout")
    else:
        assert events[-1]["event"] == "completed"


async def test_http_provider_failure_has_same_safe_category(client, monkeypatch):
    async def no_ingest(*_args):
        return False

    async def fail(*_args):
        raise APIStatusError(
            "PRIVATE",
            response=httpx.Response(429, request=httpx.Request("POST", "https://example.test")),
            body={"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDay"}]}]}},
        )

    monkeypatch.setattr(research_mod, "_needs_auto_ingest", no_ingest)
    monkeypatch.setattr(research_mod, "run_research", fail)
    response = client.post("/research/AAPL?fresh=true")
    assert response.status_code == 502
    assert response.json()["detail"]["kind"] == "provider_daily_limit"
    assert "PRIVATE" not in response.text


async def test_independent_filing_answers_emit_actual_completion_events(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.agents.nodes import sec_agent as sec_mod

    events = []
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Grounded fixture answer."))]
    )
    create = AsyncMock(return_value=response)
    monkeypatch.setattr(
        sec_mod,
        "_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
    )
    monkeypatch.setattr(sec_mod, "record_chat", lambda *_args: None)
    monkeypatch.setattr(sec_mod, "emit_progress", events.append)
    import asyncio

    await asyncio.gather(
        *(
            sec_mod._summarize(question, ["Real fixture text"])
            for question in sec_mod.CANONICAL_QUESTIONS
        )
    )
    assert create.await_count == 4
    assert sorted(event["index"] for event in events) == [0, 1, 2, 3]
    assert all(event["kind"] == "filing_question" for event in events)


async def test_pacing_emits_wait_only_when_a_request_really_waits(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.config import get_settings
    from app.services import llm as llm_mod

    monkeypatch.setenv("LLM_MIN_INTERVAL_SECONDS", "13")
    get_settings.cache_clear()
    events = []
    sleep = AsyncMock()
    monkeypatch.setattr(llm_mod, "_pacing_lock", asyncio.Lock())
    monkeypatch.setattr(llm_mod, "_last_chat_started", None)
    monkeypatch.setattr(llm_mod, "time", SimpleNamespace(monotonic=lambda: 10.0))
    monkeypatch.setattr(llm_mod, "asyncio", SimpleNamespace(sleep=sleep))
    monkeypatch.setattr(llm_mod, "emit_progress", events.append)
    request = httpx.Request("POST", "https://example.test/chat/completions")
    await llm_mod._pace_chat_request(request)
    assert events == []
    await llm_mod._pace_chat_request(request)
    sleep.assert_awaited_once_with(13.0)
    assert [event["phase"] for event in events] == ["started", "done"]
    assert events[0]["id"] == events[1]["id"]
    assert all(event["reason"] == "queue" for event in events)
