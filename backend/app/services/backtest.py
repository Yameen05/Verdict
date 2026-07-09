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


class BacktestSummary(BaseModel):
    total_runs: int = 0
    scored: int = 0
    hits: int = 0
    immature: int = 0
    hit_rate: float | None = None
    avg_return_pct: float | None = None
    by_horizon: list[HorizonStat] = Field(default_factory=list)
    rule: str = (
        f"Each verdict is graded at its own horizon: Buy hits if price rose, "
        f"Sell if it fell, Hold within ±{HOLD_BAND_PCT:.0f}%. Verdicts whose "
        f"horizon has not elapsed are 'immature'."
    )


class BacktestResponse(BaseModel):
    entries: list[BacktestEntry] = Field(default_factory=list)
    summary: BacktestSummary


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

    for run in runs:
        horizon = run.horizon_days or default_horizon_days
        entry = BacktestEntry(
            id=run.id,
            ticker=run.ticker,
            recommendation=run.recommendation,
            confidence=run.confidence,
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

    summary = BacktestSummary(
        total_runs=len(runs),
        scored=scored,
        hits=hits,
        immature=immature,
        hit_rate=round(hits / scored, 4) if scored else None,
        avg_return_pct=round(sum(all_returns) / len(all_returns), 2) if all_returns else None,
        by_horizon=by_horizon,
    )
    return BacktestResponse(entries=entries, summary=summary)
