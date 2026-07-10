"""Backtest the scoreboard — grade each past verdict at its stated horizon.

The scoreboard measures return from verdict *to now*. This goes further: for
every persisted verdict it looks up the price `horizon_days` later (the horizon
the verdict actually committed to) and asks whether the call was right *by then*.
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
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from app.services.metrics_client import PriceBar

HOLD_BAND_PCT = 5.0
DEFAULT_HORIZON_DAYS = 14

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
    # Model that issued the verdict; keeps hit rates comparable across swaps.
    model: str | None = None
    horizon_days: int
    created_at: datetime
    evaluated_at: str | None = None
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
    """Calibration check: did high-confidence calls actually hit more often?"""

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
    # Mean squared gap between stated confidence and the 0/1 outcome across
    # matured calls. 0 is perfect; 0.25 is what always saying 50% would score.
    brier_score: float | None = None
    rule: str = (
        f"Each verdict is graded at its own horizon: Buy hits if price rose, "
        f"Sell if it fell, Hold within ±{HOLD_BAND_PCT:.0f}%. Verdicts whose "
        f"horizon has not elapsed are 'immature'."
    )


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
    """Bucketed hit rates + Brier score from (confidence, hit) pairs."""
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


def _close_on_or_after(bars: list[PriceBar], target: datetime) -> PriceBar | None:
    """First daily bar dated on/after the target date (bars are chronological)."""
    for bar in bars:
        if _bar_date(bar) >= target:
            return bar
    return None


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
        horizon = run.horizon_days or default_horizon_days
        entry = BacktestEntry(
            id=run.id,
            ticker=run.ticker,
            recommendation=run.recommendation,
            confidence=run.confidence,
            # getattr: legacy RunLike fakes in tests may not carry the field.
            model=getattr(run, "llm_model", None),
            horizon_days=horizon,
            created_at=run.created_at,
            price_at_run=run.price_at_run,
        )

        if run.price_at_run and run.recommendation in {"Buy", "Sell", "Hold"}:
            created = run.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            eval_date = created + timedelta(days=horizon)
            if eval_date > now:
                entry.outcome = "immature"
                immature += 1
            else:
                bars = histories.get(run.ticker.upper()) or []
                exit_bar = _close_on_or_after(bars, eval_date)
                if exit_bar is not None:
                    ret = (exit_bar.close - run.price_at_run) / run.price_at_run * 100.0
                    entry.price_at_horizon = round(exit_bar.close, 4)
                    entry.evaluated_at = exit_bar.time
                    entry.return_pct = round(ret, 2)
                    entry.outcome = _outcome(run.recommendation, ret)
                    scored += 1
                    hits += entry.outcome == "hit"
                    all_returns.append(ret)
                    if run.confidence is not None:
                        scored_confidence.append(
                            (run.confidence, entry.outcome == "hit")
                        )
                    horizon_buckets.setdefault(horizon, []).append(ret)
                    horizon_hits[horizon] = horizon_hits.get(horizon, 0) + (
                        entry.outcome == "hit"
                    )
                # else: no price data at/after the horizon → left unscored.

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
