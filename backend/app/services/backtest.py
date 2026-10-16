"""Backtest the scoreboard — grade each past verdict at its stated horizon.

The scoreboard and backtest share the same deadline and completed daily-candle
evaluation. Finalized results are reused so later prices cannot change a grade.
Verdicts whose horizon has not elapsed yet are reported as "immature".

The scoring rule matches the scoreboard so the two read consistently:
  Buy  is a hit if the price rose over the horizon,
  Sell is a hit if it fell,
  Hold is a hit if it stayed within ±HOLD_BAND_PCT.

`compute_backtest` is pure: it takes already-fetched daily histories and does no
I/O, so it is fully unit-testable. The router handles fetching/caching.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.services.assessment import analysis_warning, assessment_failure_reason, prediction_kind
from app.services.metrics_client import PriceBar

HOLD_BAND_PCT = 5.0
DEFAULT_HORIZON_DAYS = 14
GRADING_RULE = (
    "Graded only after the selected calendar-day holding period ends. "
    "Uses the first fully completed daily candle ending at or after the deadline "
    "(the next available candle when markets are closed). "
    "Buy hits above the issue price; Sell hits below it; Hold hits within ±5%. "
    "Open and unavailable-price calls are excluded from performance statistics."
)

Outcome = Literal["hit", "miss", "immature", "unscored"]


class RunLike(Protocol):
    id: int
    ticker: str
    recommendation: str
    confidence: int | None
    horizon_days: int | None
    price_at_run: float | None
    created_at: datetime


class BacktestEntry(BaseModel):
    id: int
    ticker: str
    recommendation: str
    confidence: int | None = None
    prediction_kind: str = "ai"
    analysis_status: str = "complete"
    analysis_warning: str | None = None
    tracking_eligible: bool = True
    # Model that issued the verdict; keeps hit rates comparable across swaps.
    model: str | None = None
    horizon_days: int | None
    created_at: datetime
    due_at: datetime | None
    evaluated_at: str | None = None
    price_bar_at: str | None = None
    status_reason: str = ""
    horizon_assumed: bool = False
    price_at_run: float | None = None
    price_at_horizon: float | None = None
    return_pct: float | None = None
    outcome: Outcome = "unscored"


class HorizonStat(BaseModel):
    horizon_days: int
    scored: int = 0
    hits: int = 0
    hit_rate: float | None = None
    avg_return_pct: float | None = None


class ConfidenceBucket(BaseModel):
    """Historical grading outcomes grouped by the recorded AI assessment score."""

    label: str  # e.g. "70-79"
    scored: int = 0
    hits: int = 0
    hit_rate: float | None = None
    avg_confidence: float | None = None


class BacktestSummary(BaseModel):
    total_runs: int = 0
    scored: int = 0
    hits: int = 0
    immature: int = 0
    hit_rate: float | None = None
    avg_return_pct: float | None = None
    by_horizon: list[HorizonStat] = Field(default_factory=list)
    by_confidence: list[ConfidenceBucket] = Field(default_factory=list)
    # Retrospective squared error treating score/100 as a probability solely
    # for this diagnostic. This does not establish calibrated profit odds.
    brier_score: float | None = Field(default=None, description="Historical squared error using assessment score/100 as a diagnostic input; not proof of calibrated profit odds")
    rule: str = GRADING_RULE


class BacktestResponse(BaseModel):
    entries: list[BacktestEntry] = Field(default_factory=list)
    summary: BacktestSummary


_CONFIDENCE_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("<50", 0, 49),
    ("50-59", 50, 59),
    ("60-69", 60, 69),
    ("70-79", 70, 79),
    ("80-100", 80, 100),
)


def _confidence_calibration(
    scored_calls: list[tuple[int, bool]],
) -> tuple[list[ConfidenceBucket], float | None]:
    """Historical diagnostic, not a calibration fit or probability validation."""
    if not scored_calls:
        return [], None
    buckets: list[ConfidenceBucket] = []
    for label, low, high in _CONFIDENCE_BUCKETS:
        members = [(c, hit) for c, hit in scored_calls if low <= c <= high]
        if not members:
            continue
        hits = sum(hit for _, hit in members)
        buckets.append(
            ConfidenceBucket(
                label=label,
                scored=len(members),
                hits=hits,
                hit_rate=round(hits / len(members), 4),
                avg_confidence=round(sum(c for c, _ in members) / len(members), 1),
            )
        )
    brier = sum((c / 100.0 - float(hit)) ** 2 for c, hit in scored_calls) / len(scored_calls)
    return buckets, round(brier, 4)


def _outcome(recommendation: str, return_pct: float) -> Literal["hit", "miss"]:
    if recommendation == "Buy":
        return "hit" if return_pct > 0 else "miss"
    if recommendation == "Sell":
        return "hit" if return_pct < 0 else "miss"
    return "hit" if abs(return_pct) <= HOLD_BAND_PCT else "miss"


def _bar_date(bar: PriceBar) -> datetime:
    """Parse a bar's ISO timestamp into a tz-aware datetime (UTC if naive)."""
    dt = datetime.fromisoformat(bar.time.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def original_horizon(run: RunLike) -> int | None:
    value = run.horizon_days
    if isinstance(value, int) and value > 0:
        return value
    payload = getattr(run, "payload", None) or {}
    value = (payload.get("report") or {}).get("horizon_days") if isinstance(payload, dict) else None
    if isinstance(value, int) and value > 0:
        return value
    saved = getattr(run, "horizon_evaluation", None)
    value = saved.get("horizon_days") if isinstance(saved, dict) else None
    return value if isinstance(value, int) and value > 0 else None


def due_at(run: RunLike, default_horizon_days: int = DEFAULT_HORIZON_DAYS) -> datetime | None:
    days = original_horizon(run)
    return as_utc(run.created_at) + timedelta(days=days) if days else None


def evaluate_run(
    run: RunLike,
    bars: list[PriceBar],
    *,
    now: datetime,
    default_horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> BacktestEntry:
    deadline = due_at(run, default_horizon_days)
    kind = prediction_kind(getattr(run, "payload", None), run.recommendation, run.confidence)
    partial = kind in {"partial_ai", "rules_based"}
    entry = BacktestEntry(
        id=run.id,
        ticker=run.ticker,
        recommendation=run.recommendation,
        confidence=None if partial or kind == "none" else run.confidence,
        prediction_kind=kind,
        analysis_status="incomplete" if partial else "failed" if kind == "none" else "complete",
        analysis_warning=analysis_warning(getattr(run, "payload", None)) if partial else None,
        tracking_eligible=False,
        model=getattr(run, "llm_model", None),
        horizon_days=original_horizon(run),
        horizon_assumed=bool((getattr(run, "horizon_evaluation", None) or {}).get("horizon_assumed", False)),
        created_at=as_utc(run.created_at),
        due_at=deadline,
        price_at_run=run.price_at_run,
    )
    now = as_utc(now)
    if kind == "none":
        entry.recommendation = "Failed"
        entry.confidence = None
        entry.status_reason = assessment_failure_reason(getattr(run, "payload", None))
        return entry
    if deadline is None:
        entry.status_reason = (
            "The original holding period was not recorded. No deadline or outcome was invented."
        )
        return entry
    if not run.price_at_run or not isfinite(run.price_at_run) or run.price_at_run <= 0:
        entry.status_reason = "No valid issue price was captured; this call cannot be graded."
        return entry
    entry.tracking_eligible = True
    if now < deadline:
        entry.outcome = "immature"
        entry.status_reason = "The original selected holding period has not ended."
        return entry

    # A final result is an immutable snapshot, not a return to today's price.
    saved = getattr(run, "horizon_evaluation", None)
    if saved:
        frozen = BacktestEntry.model_validate(saved)
        return frozen.model_copy(
            update={
                "prediction_kind": kind,
                "analysis_status": entry.analysis_status,
                "analysis_warning": entry.analysis_warning,
                "confidence": entry.confidence,
                "tracking_eligible": True,
            }
        )

    # Daily candles are timestamped at their start, not at their final close.
    # Treat them as complete only once the full daily interval has ended. This
    # also avoids publishing a grade from today's still-changing daily candle.
    candidates = []
    for bar in bars:
        try:
            end = _bar_date(bar) + timedelta(days=1)
        except (ValueError, TypeError):
            continue
        if deadline <= end <= now and isfinite(bar.close) and bar.close > 0:
            candidates.append((end, bar))
    if not candidates:
        entry.status_reason = (
            "Waiting for a completed daily candle at or after the deadline. "
            "The market may be closed or price data may be unavailable."
        )
        return entry
    end, bar = min(candidates, key=lambda pair: pair[0])
    ret = (bar.close - run.price_at_run) / run.price_at_run * 100.0
    entry.price_at_horizon = round(bar.close, 4)
    entry.price_bar_at = bar.time
    entry.evaluated_at = end.isoformat()
    entry.return_pct = round(ret, 2)
    entry.outcome = _outcome(run.recommendation, ret)
    direction = "rose" if ret > 0 else "fell" if ret < 0 else "was unchanged"
    entry.status_reason = (
        f"Price {direction} {abs(ret):.2f}% from the issue price. "
        + {
            "Buy": "Buy requires a positive return.",
            "Sell": "Sell requires a negative return.",
            "Hold": "Hold requires a return within ±5%.",
        }[run.recommendation]
    )
    return entry


def compute_backtest(
    runs: list[RunLike],
    histories: dict[str, list[PriceBar]],
    *,
    now: datetime | None = None,
    default_horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> BacktestResponse:
    now = now or datetime.now(UTC)
    entries: list[BacktestEntry] = []
    horizon_buckets: dict[int, list[float]] = {}
    horizon_hits: dict[int, int] = {}
    scored = 0
    hits = 0
    immature = 0
    all_returns: list[float] = []
    scored_confidence: list[tuple[int, bool]] = []

    for run in runs:
        entry = evaluate_run(
            run,
            histories.get(run.ticker.upper()) or [],
            now=now,
            default_horizon_days=default_horizon_days,
        )
        if entry.outcome == "immature":
            immature += 1
        elif entry.outcome in {"hit", "miss"}:
            ret = entry.return_pct
            scored += 1
            hits += entry.outcome == "hit"
            all_returns.append(ret)
            if entry.confidence is not None:
                scored_confidence.append((entry.confidence, entry.outcome == "hit"))
            horizon_buckets.setdefault(entry.horizon_days, []).append(ret)
            horizon_hits[entry.horizon_days] = horizon_hits.get(entry.horizon_days, 0) + (
                entry.outcome == "hit"
            )

        entries.append(entry)

    by_horizon = [
        HorizonStat(
            horizon_days=h,
            scored=len(rets),
            hits=horizon_hits.get(h, 0),
            hit_rate=round(horizon_hits.get(h, 0) / len(rets), 4) if rets else None,
            avg_return_pct=round(sum(rets) / len(rets), 2) if rets else None,
        )
        for h, rets in sorted(horizon_buckets.items())
    ]

    by_confidence, brier = _confidence_calibration(scored_confidence)
    summary = BacktestSummary(
        total_runs=len(runs),
        scored=scored,
        hits=hits,
        immature=immature,
        hit_rate=round(hits / scored, 4) if scored else None,
        avg_return_pct=round(sum(all_returns) / len(all_returns), 2) if all_returns else None,
        by_horizon=by_horizon,
        by_confidence=by_confidence,
        brier_score=brier,
    )
    return BacktestResponse(entries=entries, summary=summary)
