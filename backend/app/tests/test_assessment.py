"""A failed HOLD/50 must never become a scored prediction, including legacy rows."""

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.persistence.db import save_run, session_scope
from app.schemas.research import ResearchResponse
from app.services.assessment import assessment_failed
from app.services.backtest import evaluate_run


def payload():
    return {
        "ticker": "AAPL",
        "sec": {"status": "ok", "findings": []},
        "news": {"status": "ok", "article_count": 0, "sentiment_score": None},
        "metrics": {"status": "ok", "current_price": 100},
        "insider": {"status": "ok"},
        "signals": {"status": "ok"},
        "bull": {"stance": "bull", "status": "ok"},
        "bear": {"stance": "bear", "status": "ok"},
        "report": {
            "ticker": "AAPL",
            "recommendation": "Hold",
            "confidence": 50,
            "justification": "Mixed signals.",
            "company_overview": "Facts",
            "financial_health": "Facts",
        },
    }


def test_degraded_hold50_projects_failure_without_changing_input():
    raw = payload()
    raw["report"]["degraded"] = True
    original = copy.deepcopy(raw)
    result = ResearchResponse.model_validate(raw)
    assert result.report.recommendation == "Failed"
    assert result.report.confidence is None
    assert result.report.assessment_status == "failed"
    assert "Failed to assess" in result.report.justification
    assert raw == original


def test_partial_with_successful_judge_retains_issued_prediction_safely():
    raw = payload()
    raw["sec"] = {"status": "error", "error": "503 PRIVATE secret"}
    result = ResearchResponse.model_validate(raw)
    assert result.report.recommendation == "Hold" and result.report.confidence is None
    assert "filing review" in result.report.analysis_warning
    assert "temporarily busy" in result.report.analysis_warning
    assert "PRIVATE" not in result.model_dump_json()


def test_complete_report_and_genuine_absence_keep_original_confidence():
    raw = payload()
    result = ResearchResponse.model_validate(raw)
    assert result.report.recommendation == "Hold" and result.report.confidence == 50
    assert result.report.assessment_status == "complete"
    assert not assessment_failed(raw)
    raw["sec"] = {"status": "skipped", "error": "Cryptocurrencies don't file reports"}
    assert ResearchResponse.model_validate(raw).report.assessment_status == "complete"


def test_legacy_failed_run_ignores_even_previously_frozen_hit():
    raw = payload()
    raw["report"]["degraded"] = True
    run = SimpleNamespace(
        id=1,
        ticker="AAPL",
        recommendation="Hold",
        confidence=50,
        created_at=datetime.now(UTC) - timedelta(days=20),
        horizon_days=14,
        price_at_run=100,
        payload=raw,
        horizon_evaluation={"outcome": "hit"},
    )
    entry = evaluate_run(run, [], now=datetime.now(UTC))
    assert entry.recommendation == "Failed" and entry.confidence is None
    assert entry.outcome == "unscored" and entry.return_pct is None
    assert run.recommendation == "Hold" and run.confidence == 50
    assert run.horizon_evaluation == {"outcome": "hit"}


async def test_history_and_chat_project_old_failure_without_rewriting_database(client, monkeypatch):
    from app.routers import ask as ask_mod
    from app.services import track_record

    raw = payload()
    raw["report"]["degraded"] = True
    async for session in session_scope():
        row = await save_run(
            session,
            user_id=None,
            ticker="AAPL",
            recommendation="Hold",
            confidence=50,
            justification="Old fallback",
            sentiment_score=None,
            price_at_run=100,
            horizon_days=14,
            payload=raw,
            llm_model="original-model",
        )
        run_id = row.id
        break
    history = client.get("/research/history/AAPL").json()["runs"][0]
    assert history["recommendation"] == "Failed" and history["confidence"] is None
    monkeypatch.setattr(
        ask_mod, "_ask_client", lambda: (_ for _ in ()).throw(AssertionError("No AI calls"))
    )
    answer = client.post(
        "/research/ask", json={"ticker": "AAPL", "question": "Should I hold?", "context": raw}
    ).json()["answer"]
    assert "Failed to assess" in answer and "50" not in answer
    monkeypatch.setattr(
        track_record,
        "daily_history",
        lambda _ticker: (_ for _ in ()).throw(AssertionError("No grading failed research")),
    )
    scoreboard = client.get("/research/scoreboard").json()
    assert scoreboard["entries"][0]["recommendation"] == "Failed"
    assert scoreboard["summary"]["scored"] == 0
    detail = client.get(f"/research/scoreboard/{run_id}").json()
    assert detail["result"]["report"]["confidence"] is None
    assert detail["entry"]["model"] == "original-model"
    from app.persistence.db import ResearchRun

    async for session in session_scope():
        stored = await session.get(ResearchRun, run_id)
        assert stored.recommendation == "Hold" and stored.confidence == 50
        assert stored.payload == raw
        break
