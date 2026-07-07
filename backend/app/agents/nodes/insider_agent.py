"""Insider activity agent.

Pulls the most recent SEC Form 4 filings for the ticker and summarizes
open-market buys vs sells. Clustered insider buying is one of the strongest
public signals that exists; heavy selling is weaker (often diversification or
tax-driven) and the summary says so.

No API key required (EDGAR is free), so unlike news this agent only skips on
upstream failure — never on configuration.
"""

from __future__ import annotations

from app.agents.state import ResearchState
from app.observability.logging import get_logger
from app.schemas.research import InsiderFindings, InsiderTransaction
from app.services.cache import TTLCache
from app.services.insider_client import (
    Form4Transaction,
    InsiderClientError,
    fetch_recent_form4,
)

log = get_logger(__name__)

_TTL_SECONDS = 1800  # 30 minutes — Form 4s don't move intraday
_cache: TTLCache[list[Form4Transaction]] = TTLCache(_TTL_SECONDS)


async def _cached_fetch(ticker: str) -> list[Form4Transaction]:
    return await _cache.get_or_set(ticker.upper(), lambda: fetch_recent_form4(ticker))


def _reset_cache() -> None:
    _cache.clear()


def _summarize(buys: list[Form4Transaction], sells: list[Form4Transaction]) -> str:
    def total(ts: list[Form4Transaction]) -> float:
        return sum(t.value_usd or 0.0 for t in ts)

    if not buys and not sells:
        return (
            "No open-market insider buys or sells in the most recent Form 4 "
            "filings (grants, option exercises, and tax withholding excluded)."
        )
    parts: list[str] = []
    if buys:
        parts.append(
            f"{len(buys)} open-market buy{'s' if len(buys) != 1 else ''}"
            + (f" (~${total(buys):,.0f})" if total(buys) else "")
        )
    if sells:
        parts.append(
            f"{len(sells)} open-market sale{'s' if len(sells) != 1 else ''}"
            + (f" (~${total(sells):,.0f})" if total(sells) else "")
        )
    lean = (
        "Insider buying with real cash is a strong positive signal."
        if len(buys) > len(sells)
        else "Insider selling alone is a weak signal (often diversification), "
        "but one-sided distribution is worth noting."
        if sells and not buys
        else "Mixed insider activity — no directional signal."
    )
    return f"Recent Form 4s show {' and '.join(parts)}. {lean}"


async def insider_agent(state: ResearchState) -> dict:
    ticker = state["ticker"]
    try:
        transactions = await _cached_fetch(ticker)
    except ValueError as e:  # unknown ticker
        return {"insider": InsiderFindings(status="error", error=str(e))}
    except InsiderClientError as e:
        log.warning("insider_unavailable", extra={"ticker": ticker, "reason": str(e)})
        return {"insider": InsiderFindings(status="skipped", error=str(e))}
    except Exception as e:  # noqa: BLE001
        log.exception("insider_unexpected_failure", extra={"ticker": ticker})
        return {"insider": InsiderFindings(status="skipped", error=f"Unexpected: {e}")}

    buys = [t for t in transactions if t.kind == "buy"]
    sells = [t for t in transactions if t.kind == "sell"]
    # Surface the directional trades first, biggest dollar value first.
    directional = sorted(
        buys + sells, key=lambda t: t.value_usd or 0.0, reverse=True
    )[:10]

    return {
        "insider": InsiderFindings(
            status="ok",
            transactions=[
                InsiderTransaction(
                    insider=t.insider,
                    role=t.role,
                    date=t.date,
                    kind=t.kind,  # type: ignore[arg-type]
                    shares=t.shares,
                    value_usd=t.value_usd,
                )
                for t in directional
            ],
            buy_count=len(buys),
            sell_count=len(sells),
            summary=_summarize(buys, sells),
        )
    }
