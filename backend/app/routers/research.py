"""Research orchestration endpoints.

  POST /research/{ticker}              run the graph, persist, return report + cost
  GET  /research/{ticker}/stream       same, but emit per-node Server-Sent Events
  GET  /research/history/{ticker}      list recent stored runs
  POST /research/ask                   conversational follow-up grounded in a prior report

The scoreboard lives in routers/scoreboard.py.
"""

# NOTE: intentionally NOT using `from __future__ import annotations` here.
# slowapi's @limiter.limit wraps each endpoint; under PEP 563 (stringized
# annotations) FastAPI resolves a handler's annotations against the *wrapper's*
# __globals__ (slowapi's module, not this one), so a Pydantic body param like
# `AskRequest` can't be resolved and is misread as a query param → HTTP 422.
# Real annotation objects sidestep that. See app/tests/test_research_ask.py.

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import (
    get_graph,
    initial_state,
    run_research,
    state_to_response,
)
from app.config import get_settings
from app.limiter import limiter
from app.observability.cost import CostTracker, start_tracking
from app.observability.logging import get_logger, get_request_id
from app.persistence.db import (
    ResearchRun,
    count_runs_since,
    latest_run_for_ticker,
    list_runs_for_ticker,
    save_run,
    session_scope,
)
from app.schemas.research import ResearchResponse

router = APIRouter()
log = get_logger(__name__)


# ----- helpers -----

def _validate_ticker(raw: str) -> str:
    t = (raw or "").strip().upper()
    if not t or len(t) > 10 or not t.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid ticker")
    return t


def _prior_run_dict(row: ResearchRun) -> dict[str, Any]:
    return {
        "recommendation": row.recommendation,
        "justification": row.justification,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "price_at_run": row.price_at_run,
    }


async def _load_prior_run(
    session: AsyncSession, ticker: str
) -> dict[str, Any] | None:
    row = await latest_run_for_ticker(session, ticker)
    return _prior_run_dict(row) if row else None


def _cache_age_minutes(row: ResearchRun) -> float:
    created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - created).total_seconds() / 60.0


async def _cached_run(session: AsyncSession, ticker: str) -> ResearchRun | None:
    """Recent run by ANY user within the cache window — research is communal."""
    ttl = get_settings().research_cache_minutes
    if ttl <= 0:
        return None
    row = await latest_run_for_ticker(session, ticker)
    if row is None or _cache_age_minutes(row) > ttl:
        return None
    try:
        # Ensure the stored payload still parses before serving it.
        ResearchResponse(**row.payload)
    except (ValidationError, TypeError):
        return None
    return row


async def _enforce_quota(session: AsyncSession, user_id: int | None) -> None:
    """Daily caps on FRESH runs — the free-tier kill-switch. Cache hits are free."""
    settings = get_settings()
    day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    if await count_runs_since(session, day_start) >= settings.daily_runs_global:
        raise HTTPException(
            status_code=429,
            detail=(
                "The community's daily research budget is used up — fresh runs "
                "reset at midnight UTC. Recent verdicts are still served instantly."
            ),
        )
    if (
        user_id is not None
        and await count_runs_since(session, day_start, user_id=user_id)
        >= settings.daily_runs_per_user
    ):
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've used your {settings.daily_runs_per_user} fresh runs for "
                "today (resets midnight UTC). Cached verdicts remain available."
            ),
        )


async def _persist(
    session: AsyncSession,
    *,
    result: ResearchResponse,
    ticker: str,
    user_id: int | None,
    duration_ms: float,
    cost_usd: float,
    request_id: str,
):
    return await save_run(
        session,
        user_id=user_id,
        ticker=ticker,
        recommendation=result.report.recommendation,
        justification=result.report.justification,
        sentiment_score=result.news.sentiment_score,
        confidence=result.report.confidence,
        price_at_run=result.metrics.current_price,
        payload=result.model_dump(),
        duration_ms=duration_ms,
        cost_usd=cost_usd,
        request_id=request_id,
    )


class ResearchEnvelope(BaseModel):
    """Wraps ResearchResponse with operational metadata."""

    request_id: str = Field(default="")
    duration_ms: float = 0.0
    cost: dict[str, Any] = Field(default_factory=dict)
    persisted_id: int | None = None
    cached: bool = False
    cache_age_minutes: float | None = None
    result: ResearchResponse


def _envelope_from_cache(row: ResearchRun, rid: str) -> ResearchEnvelope:
    return ResearchEnvelope(
        request_id=rid,
        duration_ms=0.0,
        cost={},
        persisted_id=row.id,
        cached=True,
        cache_age_minutes=round(_cache_age_minutes(row), 1),
        result=ResearchResponse(**row.payload),
    )


class HistoryEntry(BaseModel):
    id: int
    ticker: str
    recommendation: str
    justification: str
    sentiment_score: float | None = None
    confidence: int | None = None
    price_at_run: float | None = None
    duration_ms: float | None = None
    cost_usd: float | None = None
    created_at: datetime


class HistoryResponse(BaseModel):
    ticker: str
    runs: list[HistoryEntry]


# ----- POST /research/{ticker} -----

@router.post("/{ticker}", response_model=ResearchEnvelope)
@limiter.limit(lambda: get_settings().rate_limit_research)
async def research(
    request: Request,
    response: Response,
    ticker: str,
    fresh: bool = False,
    session: AsyncSession = Depends(session_scope),
) -> ResearchEnvelope:
    ticker = _validate_ticker(ticker)
    tracker = start_tracking()
    rid = get_request_id()

    if not fresh:
        cached = await _cached_run(session, ticker)
        if cached is not None:
            log.info("research_cache_hit", extra={"ticker": ticker, "run_id": cached.id})
            return _envelope_from_cache(cached, rid)

    await _enforce_quota(session, request.state.user_id)
    log.info("research_started", extra={"ticker": ticker})

    prior_run = await _load_prior_run(session, ticker)

    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            run_research(ticker, prior_run),
            timeout=get_settings().request_timeout_seconds,
        )
    except TimeoutError as e:
        log.warning("research_timeout", extra={"ticker": ticker})
        raise HTTPException(status_code=504, detail="Research timed out") from e
    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    cost_payload = tracker.to_dict()
    response.headers["x-cost-usd"] = f"{tracker.total_usd:.6f}"
    response.headers["x-duration-ms"] = f"{duration_ms:.2f}"

    run = await _persist(
        session,
        result=result,
        ticker=ticker,
        user_id=request.state.user_id,
        duration_ms=duration_ms,
        cost_usd=tracker.total_usd,
        request_id=rid,
    )
    log.info(
        "research_completed",
        extra={
            "ticker": ticker,
            "recommendation": result.report.recommendation,
            "confidence": result.report.confidence,
            "duration_ms": duration_ms,
            "cost_usd": tracker.total_usd,
            "run_id": run.id,
        },
    )

    return ResearchEnvelope(
        request_id=rid,
        duration_ms=duration_ms,
        cost=cost_payload,
        persisted_id=run.id,
        result=result,
    )


# ----- GET /research/{ticker}/stream -----

async def _sse_stream(
    ticker: str,
    tracker: CostTracker,
    rid: str,
    user_id: int,
    prior_run: dict[str, Any] | None,
):
    """Run the graph via astream() and emit SSE events.

    Two stream modes are multiplexed: "updates" (a node finished — same events
    the UI always had) and "custom" (mid-node debate/judge progress emitted by
    the advocates and the judge via get_stream_writer()).
    """
    graph = get_graph()
    started = time.perf_counter()

    yield {
        "event": "started",
        "data": json.dumps({"ticker": ticker, "request_id": rid}),
    }

    final_state: dict = {}
    try:
        async for mode, chunk in graph.astream(
            initial_state(ticker, prior_run), stream_mode=["updates", "custom"]
        ):
            if mode == "custom":
                yield {"event": "debate", "data": json.dumps(chunk, default=str)}
                continue
            # `chunk` is {node_name: partial_state}
            for node_name, partial in chunk.items():
                final_state.update(partial or {})
                yield {
                    "event": "node_completed",
                    "data": json.dumps(
                        {"node": node_name, "payload": _serializable(partial or {})},
                        default=str,
                    ),
                }
    except Exception as e:  # noqa: BLE001
        log.exception("research_stream_failed", extra={"ticker": ticker})
        yield {
            "event": "error",
            "data": json.dumps(
                {"detail": "Research stream failed", "error_type": type(e).__name__}
            ),
        }
        return

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    result = state_to_response(ticker, final_state)

    # Persist (best-effort; SSE consumer doesn't need to wait).
    persisted_id = None
    try:
        async for session in session_scope():
            run = await _persist(
                session,
                result=result,
                ticker=ticker,
                user_id=user_id,
                duration_ms=duration_ms,
                cost_usd=tracker.total_usd,
                request_id=rid,
            )
            persisted_id = run.id
            break
    except Exception:  # noqa: BLE001
        log.exception("research_stream_persist_failed", extra={"ticker": ticker})

    yield {
        "event": "completed",
        "data": json.dumps(
            {
                "request_id": rid,
                "duration_ms": duration_ms,
                "cost": tracker.to_dict(),
                "persisted_id": persisted_id,
                "cached": False,
                "result": result.model_dump(),
            },
            default=str,
        ),
    }


async def _sse_cached(row: ResearchRun, rid: str, ticker: str):
    """Serve a cache hit over the same SSE contract: started → completed."""
    envelope = _envelope_from_cache(row, rid)
    yield {
        "event": "started",
        "data": json.dumps({"ticker": ticker, "request_id": rid}),
    }
    yield {
        "event": "completed",
        "data": json.dumps(
            {
                "request_id": rid,
                "duration_ms": 0.0,
                "cost": {},
                "persisted_id": row.id,
                "cached": True,
                "cache_age_minutes": envelope.cache_age_minutes,
                "result": envelope.result.model_dump(),
            },
            default=str,
        ),
    }


def _serializable(d: dict) -> dict:
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, list):
            out[k] = [i.model_dump() if hasattr(i, "model_dump") else i for i in v]
        else:
            out[k] = v.model_dump() if hasattr(v, "model_dump") else v
    return out


@router.get("/{ticker}/stream")
@limiter.limit(lambda: get_settings().rate_limit_research)
async def research_stream(
    request: Request,
    ticker: str,
    fresh: bool = False,
    session: AsyncSession = Depends(session_scope),
) -> EventSourceResponse:
    ticker = _validate_ticker(ticker)
    tracker = start_tracking()
    rid = get_request_id()

    if not fresh:
        cached = await _cached_run(session, ticker)
        if cached is not None:
            log.info("research_cache_hit", extra={"ticker": ticker, "run_id": cached.id})
            return EventSourceResponse(_sse_cached(cached, rid, ticker))

    await _enforce_quota(session, request.state.user_id)
    # Load the prior run up front (into a plain dict) so the stream generator
    # never touches this request-scoped session after the response starts.
    prior_run = await _load_prior_run(session, ticker)
    log.info("research_stream_started", extra={"ticker": ticker})
    return EventSourceResponse(
        _sse_stream(ticker, tracker, rid, request.state.user_id, prior_run)
    )


# ----- GET /research/history/{ticker} -----

@router.get("/history/{ticker}", response_model=HistoryResponse)
async def history(
    request: Request,
    ticker: str,
    limit: int = 20,
    session: AsyncSession = Depends(session_scope),
) -> HistoryResponse:
    ticker = _validate_ticker(ticker)
    # Research runs are communal in the multi-user model: everyone sees the
    # shared record (that's what makes the cache and scoreboard honest).
    rows = await list_runs_for_ticker(
        session,
        ticker,
        limit=min(max(limit, 1), 100),
    )
    return HistoryResponse(
        ticker=ticker,
        runs=[
            HistoryEntry(
                id=r.id,
                ticker=r.ticker,
                recommendation=r.recommendation,
                justification=r.justification,
                sentiment_score=r.sentiment_score,
                confidence=r.confidence,
                price_at_run=r.price_at_run,
                duration_ms=r.duration_ms,
                cost_usd=r.cost_usd,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )
