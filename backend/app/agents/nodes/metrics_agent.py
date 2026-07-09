"""Financial Metrics agent.

Pulls trailing twelve-month financial metrics for the ticker via yfinance,
plus holding-period stats (what this asset typically does over the user's
chosen window) computed from a year of daily closes. Results are cached so a
burst of /research calls for the same ticker only hits Yahoo once.
"""

from __future__ import annotations

import asyncio

from app.agents.state import ResearchState
from app.observability.logging import get_logger
from app.schemas.research import MetricsFindings
from app.services.cache import TTLCache
from app.services.metrics_client import (
    HorizonStats,
    Metrics,
    MetricsClientError,
    fetch_horizon_stats,
    fetch_metrics,
)

log = get_logger(__name__)
_TTL_SECONDS = 600  # 10 minutes
_cache: TTLCache[Metrics] = TTLCache(_TTL_SECONDS)
_stats_cache: TTLCache[HorizonStats] = TTLCache(_TTL_SECONDS)

DEFAULT_HORIZON_DAYS = 14


async def _cached_fetch(ticker: str) -> Metrics:
    async def factory() -> Metrics:
        return await asyncio.to_thread(fetch_metrics, ticker)

    return await _cache.get_or_set(ticker.upper(), factory)


async def _cached_stats(ticker: str, horizon_days: int) -> HorizonStats:
    async def factory() -> HorizonStats:
        return await asyncio.to_thread(fetch_horizon_stats, ticker, horizon_days)

    return await _stats_cache.get_or_set(f"{ticker.upper()}:{horizon_days}", factory)


async def metrics_agent(state: ResearchState) -> dict:
    ticker = state["ticker"]
    horizon = state.get("horizon_days") or DEFAULT_HORIZON_DAYS
    try:
        metrics = await _cached_fetch(ticker)
    except MetricsClientError as e:
        log.warning("metrics_unavailable", extra={"ticker": ticker, "reason": str(e)})
        return {"metrics": MetricsFindings(status="error", error=str(e))}
    except Exception as e:  # noqa: BLE001
        log.exception("metrics_unexpected_failure", extra={"ticker": ticker})
        return {"metrics": MetricsFindings(status="error", error=f"Unexpected: {e}")}

    # Horizon stats are best-effort — thin history shouldn't sink the metrics.
    stats: HorizonStats | None = None
    try:
        stats = await _cached_stats(ticker, horizon)
    except MetricsClientError as e:
        log.warning("horizon_stats_unavailable", extra={"ticker": ticker, "reason": str(e)})
    except Exception:  # noqa: BLE001
        log.exception("horizon_stats_failure", extra={"ticker": ticker})

    return {
        "metrics": MetricsFindings(
            status="ok",
            revenue=metrics.revenue,
            eps=metrics.eps,
            pe_ratio=metrics.pe_ratio,
            profit_margin=metrics.profit_margin,
            debt_to_equity=metrics.debt_to_equity,
            week_52_low=metrics.week_52_low,
            week_52_high=metrics.week_52_high,
            current_price=metrics.current_price,
            horizon_days=stats.horizon_days if stats else horizon,
            recent_return_pct=stats.recent_return_pct if stats else None,
            typical_swing_pct=stats.typical_swing_pct if stats else None,
            best_window_pct=stats.best_window_pct if stats else None,
            worst_window_pct=stats.worst_window_pct if stats else None,
        )
    }


# Test helper.
def _reset_cache() -> None:
    _cache.clear()
    _stats_cache.clear()
