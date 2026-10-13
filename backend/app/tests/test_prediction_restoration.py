"""Issued predictions survive partial execution without invented confidence/data."""

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.persistence.db import ResearchRun, get_sessionmaker, save_run
from app.routers import scoreboard as scoreboard_mod
from app.schemas.research import ResearchResponse
from app.services import track_record
from app.services.assessment import prediction_kind
from app.services.backtest import evaluate_run
from app.services.metrics_client import PriceBar

ISSUED = datetime(2026, 10, 12, 23, 37, 40, tzinfo=UTC)


def payload(rec="Sell", conf=80):
    return {
        "ticker": "NVDA",
        "sec": {"status": "error", "error": "429 EmbedContentRequestsPerMinute PRIVATE"},
        "news": {"status": "ok", "article_count": 0},
        "metrics": {"status": "ok", "current_price": 226.32},
        "bull": {"stance": "bull", "status": "ok"},
        "bear": {"stance": "bear", "status": "ok"},
        "report": {
            "ticker": "NVDA",
            "recommendation": rec,
            "confidence": conf,
            "horizon_days": 7,
            "justification": "Original issued prediction.",
            "company_overview": "Original facts.",
            "financial_health": "Original facts.",
        },
    }


def run(raw=None, **overrides):
    values = dict(
        id=1,
        ticker="NVDA",
        recommendation="Sell",
        confidence=80,
        horizon_days=7,
        price_at_run=226.32,
        created_at=ISSUED,
        payload=raw or payload(),
        llm_model="gemini-2.5-flash",
        horizon_evaluation=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_legacy_sell_with_filing_failure_keeps_exact_original_clock_and_price():
    original = run()
    entry = evaluate_run(original, [], now=ISSUED + timedelta(days=6))
    assert entry.outcome == "immature" and entry.tracking_eligible
    assert entry.recommendation == "Sell" and entry.confidence is None
    assert entry.prediction_kind == "partial_ai" and entry.analysis_status == "incomplete"
    assert "per-minute quota" in entry.analysis_warning and "PRIVATE" not in entry.analysis_warning
    assert entry.due_at == ISSUED + timedelta(days=7) and entry.price_at_run == 226.32
    assert original.confidence == 80 and original.recommendation == "Sell"


def test_partial_prediction_scores_only_at_deadline_without_changing_source():
    original = run()
    raw = copy.deepcopy(original.payload)
    due = ISSUED + timedelta(days=7)
    bars = [
        PriceBar(
            time=(due - timedelta(days=1)).isoformat(),
            open=200,
            high=200,
            low=200,
            close=200,
            volume=1,
        )
    ]
    assert evaluate_run(original, bars, now=due - timedelta(seconds=1)).outcome == "immature"
    entry = evaluate_run(original, bars, now=due)
    assert entry.outcome == "hit" and entry.price_at_horizon == 200
    assert entry.confidence is None and entry.prediction_kind == "partial_ai"
    assert original.payload == raw and original.confidence == 80


def test_existing_frozen_grade_is_projected_without_rewriting_original_snapshot():
    original = run()
    saved = evaluate_run(
        original,
        [
            PriceBar(
                time=(ISSUED + timedelta(days=6)).isoformat(),
                open=200,
                high=200,
                low=200,
                close=200,
                volume=1,
            )
        ],
        now=ISSUED + timedelta(days=8),
    ).model_dump(mode="json")
    saved["confidence"] = 80
    saved.pop("prediction_kind")
    original.horizon_evaluation = copy.deepcopy(saved)
    entry = evaluate_run(original, [], now=ISSUED + timedelta(days=20))
    assert entry.outcome == "hit" and entry.price_at_horizon == 200 and entry.confidence is None
    assert original.horizon_evaluation == saved


def test_partial_report_and_export_projection_keep_issued_call_and_hide_confidence():
    raw = payload()
    before = copy.deepcopy(raw)
    result = ResearchResponse.model_validate(raw)
    assert result.report.recommendation == "Sell" and result.report.confidence is None
    assert (
        result.report.prediction_kind == "partial_ai"
        and result.report.assessment_status == "incomplete"
    )
    assert result.report.justification == "Original issued prediction."
    assert (
        "filing review" in result.report.analysis_warning
        and "PRIVATE" not in result.model_dump_json()
    )
    assert raw == before


@pytest.mark.parametrize("rec", ["Failed", "Pending"])
def test_a_failed_or_pending_result_is_never_resurrected(rec):
    original = run(payload(rec, None), recommendation=rec, confidence=None)
    entry = evaluate_run(original, [], now=ISSUED + timedelta(days=8))
    assert entry.recommendation == "Failed" and entry.prediction_kind == "none"
    assert not entry.tracking_eligible and entry.return_pct is None


def test_explicit_rules_buy_is_trackable_but_automatic_hold50_is_not():
    raw = payload("Buy", 58)
    raw["report"].update(
        degraded=True,
        justification="The AI judge was unavailable, so this is a conservative fallback verdict from the data already collected.",
    )
    original = run(raw, recommendation="Buy", confidence=58)
    entry = evaluate_run(original, [], now=ISSUED + timedelta(days=1))
    assert entry.outcome == "immature" and entry.prediction_kind == "rules_based"
    assert entry.confidence is None and entry.analysis_warning
    raw["report"].update(recommendation="Hold", confidence=50)
    assert prediction_kind(raw, "Hold", 50) == "none"
    # A real judge-issued Hold/50 is distinct from that automatic placeholder.
    assert prediction_kind(payload("Hold", 50), "Hold", 50) == "partial_ai"


def test_missing_baseline_or_horizon_does_not_invent_an_outcome():
    missing_price = evaluate_run(run(price_at_run=None), [], now=ISSUED + timedelta(days=1))
    assert not missing_price.tracking_eligible and missing_price.outcome == "unscored"
    raw = payload()
    raw["report"].pop("horizon_days")
    missing_horizon = evaluate_run(run(raw, horizon_days=None), [], now=ISSUED + timedelta(days=30))
    assert missing_horizon.due_at is None and missing_horizon.horizon_days is None
    assert not missing_horizon.tracking_eligible


async def test_restored_partial_is_persistently_graded_and_stats_separate_rules(
    client, monkeypatch
):
    now = ISSUED + timedelta(days=7)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz else now.replace(tzinfo=None)

    monkeypatch.setattr(scoreboard_mod, "datetime", Clock)
    monkeypatch.setattr(track_record, "datetime", Clock)

    async def prices(_ticker):
        return [
            PriceBar(
                time=(now - timedelta(days=1)).isoformat(),
                open=200,
                high=200,
                low=200,
                close=200,
                volume=1,
            )
        ]

    monkeypatch.setattr(track_record, "daily_history", prices)
    original = payload()
    async with get_sessionmaker()() as session:
        row = await save_run(
            session,
            ticker="NVDA",
            recommendation="Sell",
            confidence=80,
            horizon_days=7,
            price_at_run=226.32,
            payload=original,
            llm_model="gemini-2.5-flash",
            justification="Original issued prediction.",
            sentiment_score=None,
        )
        row.created_at = ISSUED
        await session.commit()
        run_id = row.id
    body = client.get("/research/scoreboard").json()
    assert body["summary"]["by_prediction_kind"]["partial_ai"]["scored"] == 1
    assert body["summary"]["by_prediction_kind"]["ai"]["scored"] == 0
    assert body["entries"][0]["outcome"] == "hit" and body["entries"][0]["confidence"] is None
    detail = client.get(f"/research/scoreboard/{run_id}").json()
    assert detail["original_prediction"]["recorded_confidence_snapshot"] == 80
    assert detail["result"]["report"]["recommendation"] == "Sell"
    async with get_sessionmaker()() as session:
        row = await session.get(ResearchRun, run_id)
        assert row.payload == original and row.confidence == 80 and row.price_at_run == 226.32
        assert row.horizon_evaluation["outcome"] == "hit"
