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
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
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
    session: AsyncSession, ticker: str, user_id: int | None
) -> dict[str, Any] | None:
    rows = await list_runs_for_ticker(session, ticker, limit=1, user_id=user_id)
    return _prior_run_dict(rows[0]) if rows else None


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
    result: ResearchResponse


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
    session: AsyncSession = Depends(session_scope),
) -> ResearchEnvelope:
    ticker = _validate_ticker(ticker)
    tracker = start_tracking()
    rid = get_request_id()
    log.info("research_started", extra={"ticker": ticker})

    prior_run = await _load_prior_run(session, ticker, request.state.user_id)

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
                "result": result.model_dump(),
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
    session: AsyncSession = Depends(session_scope),
) -> EventSourceResponse:
    ticker = _validate_ticker(ticker)
    tracker = start_tracking()
    rid = get_request_id()
    # Load the prior run up front (into a plain dict) so the stream generator
    # never touches this request-scoped session after the response starts.
    prior_run = await _load_prior_run(session, ticker, request.state.user_id)
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
    rows = await list_runs_for_ticker(
        session,
        ticker,
        limit=min(max(limit, 1), 100),
        user_id=request.state.user_id,
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
