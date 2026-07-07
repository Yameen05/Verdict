"""Financial Metrics agent — Phase 4 + production polish.

Pulls trailing twelve-month financial metrics for the ticker via yfinance and
maps them into MetricsFindings. Results are cached for `_TTL` seconds so a
burst of /research calls for the same ticker only hits Yahoo once.
"""

from __future__ import annotations

import asyncio

from app.agents.state import ResearchState
from app.observability.logging import get_logger
from app.schemas.research import MetricsFindings
from app.services.cache import TTLCache
from app.services.metrics_client import Metrics, MetricsClientError, fetch_metrics

log = get_logger(__name__)
_TTL_SECONDS = 600  # 10 minutes
_cache: TTLCache[Metrics] = TTLCache(_TTL_SECONDS)


async def _cached_fetch(ticker: str) -> Metrics:
    async def factory() -> Metrics:
        return await asyncio.to_thread(fetch_metrics, ticker)

    return await _cache.get_or_set(ticker.upper(), factory)


async def metrics_agent(state: ResearchState) -> dict:
    ticker = state["ticker"]
    try:
        metrics = await _cached_fetch(ticker)
    except MetricsClientError as e:
        log.warning("metrics_unavailable", extra={"ticker": ticker, "reason": str(e)})
        return {"metrics": MetricsFindings(status="error", error=str(e))}
    except Exception as e:  # noqa: BLE001
        log.exception("metrics_unexpected_failure", extra={"ticker": ticker})
        return {"metrics": MetricsFindings(status="error", error=f"Unexpected: {e}")}

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
        )
    }


# Test helper.
def _reset_cache() -> None:
    _cache.clear()
