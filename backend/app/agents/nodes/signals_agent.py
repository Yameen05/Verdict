"""External market-signal agent.

Pulls optional sources that are not part of the core SEC/news/Yahoo pipeline:
analyst recommendations, earnings dates, additional quotes, macro regime, and
retail sentiment. All providers are best-effort and key-gated.
"""

from __future__ import annotations

from app.agents.state import ResearchState
from app.observability.logging import get_logger
from app.schemas.research import SignalFindings
from app.services.signals.aggregate import gather_market_signals, reset_signal_cache

log = get_logger(__name__)


async def signals_agent(state: ResearchState) -> dict:
    ticker = state["ticker"]
    try:
        signals = await gather_market_signals(ticker)
    except Exception as e:  # noqa: BLE001 - optional context must not sink research
        log.exception("signals_agent_failed", extra={"ticker": ticker})
        return {"signals": SignalFindings(status="error", error=f"Unexpected: {e}")}

    if not signals.sources_available:
        return {
            "signals": SignalFindings(
                status="skipped",
                sources_available=[],
                error="No optional market-signal providers configured.",
            )
        }
    if not signals.sources_used:
        return {
            "signals": SignalFindings(
                status="skipped",
                sources_available=signals.sources_available,
                error="Configured signal providers returned no usable data.",
            )
        }

    return {
        "signals": SignalFindings(
            status="ok",
            analyst=signals.analyst,
            retail=signals.retail,
            macro=signals.macro,
            fundamentals=signals.fundamentals,
            quotes=signals.quotes,
            earnings_days=signals.earnings_days,
            sources_used=signals.sources_used,
            sources_available=signals.sources_available,
        )
    }


def _reset_cache() -> None:
    reset_signal_cache()
