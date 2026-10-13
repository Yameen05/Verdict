"""Eligibility depends on the original analysis, never the active model version."""

from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.persistence.db import ResearchRun, get_sessionmaker, save_run
from app.routers import scoreboard as scoreboard_mod
from app.services import track_record
from app.services.assessment import assessment_failed, assessment_failure_reason
from app.services.metrics_client import PriceBar

NOW = datetime(2026, 10, 12, 23, 40, tzinfo=UTC)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    monkeypatch.setattr(scoreboard_mod, "datetime", Clock)
    monkeypatch.setattr(track_record, "datetime", Clock)
    monkeypatch.setenv("LLM_MODEL", "gemini-3.8-flash")
    get_settings.cache_clear()

    async def unexpected_price(_ticker):
        pytest.fail("No price request is needed for future or failed assessments")

    monkeypatch.setattr(track_record, "daily_history", unexpected_price)


def legacy_payload():
    # A valid old report may predate degraded, assessment_status, and debate fields.
    return {
        "report": {
            "recommendation": "Sell",
            "confidence": 75,
            "justification": "Original prediction",
        },
        "sec": {"status": "skipped"},
        "news": {"status": "ok", "article_count": 0, "sentiment_score": None},
        "metrics": {"status": "ok"},
    }


async def seed(payload, *, model="gemini-2.5-flash", days=7, issued=NOW, price=226.32):
    async with get_sessionmaker()() as session:
        row = await save_run(
            session,
            ticker="NVDA",
            recommendation=(payload.get("report") or {}).get("recommendation", "Sell"),
            confidence=(payload.get("report") or {}).get("confidence", 75),
            justification="Original prediction",
            sentiment_score=None,
            horizon_days=days,
            price_at_run=price,
            payload=payload,
            llm_model=model,
        )
        row.created_at = issued
        await session.commit()
        return row.id


async def test_old_and_new_models_completed_today_stay_open_at_original_horizons(client):
    old = await seed(legacy_payload(), days=7)
    new = await seed(legacy_payload(), model="gemini-3.8-flash", days=30)
    body = client.get("/research/scoreboard").json()
    assert body["summary"]["in_progress"] == 2
    assert body["summary"]["failed"] == body["summary"]["unscored"] == 0
    entries = {e["id"]: e for e in body["entries"]}
    assert entries[old]["model"] == "gemini-2.5-flash"
    assert entries[new]["model"] == "gemini-3.8-flash"
    for run_id, days in ((old, 7), (new, 30)):
        entry = entries[run_id]
        assert entry["outcome"] == "in_progress"
        assert entry["recommendation"] == "Sell" and entry["confidence"] == 75
        assert datetime.fromisoformat(entry["due_at"]) == NOW + timedelta(days=days)
        assert entry["price_at_run"] == 226.32 and entry["price_at_horizon"] is None
        assert entry["return_pct"] is None


async def test_partial_prediction_stays_open_while_hold50_placeholder_is_excluded(client):
    raw = legacy_payload()
    raw["sec"] = {"status": "error", "error": "401 UNAUTHENTICATED PRIVATE"}
    partial = await seed(raw)
    degraded = legacy_payload()
    degraded["report"].update(recommendation="Hold", confidence=50, degraded=True)
    fallback = await seed(degraded, model="gemini-2.0-flash")
    body = client.get("/research/scoreboard").json()
    assert body["summary"]["failed"] == 1
    assert body["summary"]["in_progress"] == 1
    assert body["summary"]["unscored"] == body["summary"]["scored"] == 0
    entries = {e["id"]: e for e in body["entries"]}
    assert "Filing review failed" in entries[partial]["analysis_warning"]
    assert "authentication" in entries[partial]["analysis_warning"]
    assert entries[partial]["outcome"] == "in_progress"
    assert entries[partial]["recommendation"] == "Sell" and entries[partial]["confidence"] is None
    assert entries[partial]["prediction_kind"] == "partial_ai"
    assert entries[fallback]["outcome"] == "failed"
    assert entries[fallback]["recommendation"] == "Failed"
    assert "PRIVATE" not in str(entries)
    async with get_sessionmaker()() as session:
        row = await session.get(ResearchRun, partial)
        assert row.payload == raw and row.recommendation == "Sell" and row.confidence == 75


async def test_missing_outcome_baseline_is_unscored_not_a_failed_assessment(client):
    await seed(legacy_payload(), issued=NOW - timedelta(days=10), price=None)
    body = client.get("/research/scoreboard").json()
    assert body["summary"]["failed"] == 0 and body["summary"]["unscored"] == 1
    assert body["entries"][0]["recommendation"] == "Sell"
    assert "issue price" in body["entries"][0]["status_reason"]


async def test_old_model_matures_and_freezes_without_changing_prediction(client, monkeypatch):
    issue = NOW - timedelta(days=7)
    run_id = await seed(legacy_payload(), issued=issue)

    async def price(_ticker):
        return [
            PriceBar(
                time=(NOW - timedelta(days=1)).isoformat(),
                open=200,
                high=200,
                low=200,
                close=200,
                volume=1,
            )
        ]

    monkeypatch.setattr(track_record, "daily_history", price)
    body = client.get("/research/scoreboard").json()
    entry = body["entries"][0]
    assert entry["outcome"] == "hit" and entry["price_at_horizon"] == 200
    assert entry["model"] == "gemini-2.5-flash"
    async with get_sessionmaker()() as session:
        row = await session.get(ResearchRun, run_id)
        assert row.recommendation == "Sell" and row.confidence == 75
        assert row.created_at.replace(tzinfo=UTC) == issue and row.price_at_run == 226.32
        assert row.horizon_days == 7 and row.payload == legacy_payload()
        assert row.horizon_evaluation["price_at_horizon"] == 200

    async def unexpected(_ticker):
        pytest.fail("An authentic frozen grade must be retained")

    monkeypatch.setattr(track_record, "daily_history", unexpected)
    assert client.get("/research/scoreboard").json()["entries"][0] == entry


@pytest.mark.parametrize("missing", ["degraded", "assessment_status", "failures"])
def test_missing_new_metadata_is_not_failure(missing):
    raw = legacy_payload()
    raw["report"].pop(missing, None)
    assert not assessment_failed(raw)


def test_recorded_legacy_rpm_reason_never_exposes_the_stored_exception():
    raw = legacy_payload()
    raw["sec"] = {"status": "error", "error": "429 quota EmbedContentRequestsPerMinute PRIVATE key"}
    assert "per-minute quota" in assessment_failure_reason(raw)
    assert "PRIVATE" not in assessment_failure_reason(raw)
