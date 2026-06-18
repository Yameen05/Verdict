"""Research orchestration endpoints.

  POST /research/{ticker}              run the graph, persist, return report + cost
  GET  /research/{ticker}/stream       same, but emit per-node Server-Sent Events
  GET  /research/history/{ticker}      list recent stored runs
  POST /research/ask                   conversational follow-up grounded in a prior report
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
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import get_graph, run_research
from app.config import get_settings
from app.limiter import limiter
from app.observability.cost import CostTracker, record_chat, start_tracking
from app.observability.logging import get_logger, get_request_id
from app.persistence.db import list_runs_for_ticker, save_run, session_scope
from app.schemas.research import (
    MetricsFindings,
    NewsFindings,
    ResearchReport,
    ResearchResponse,
    SECFindings,
)
from app.services.llm import llm_key_configured, make_llm_client

router = APIRouter()
log = get_logger(__name__)


# ----- helpers -----

def _validate_ticker(raw: str) -> str:
    t = (raw or "").strip().upper()
    if not t or len(t) > 10 or not t.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid ticker")
    return t


def _state_to_response(ticker: str, state: dict) -> ResearchResponse:
    return ResearchResponse(
        ticker=ticker,
        sec=state.get("sec") or SECFindings(status="skipped"),
        news=state.get("news") or NewsFindings(status="skipped"),
        metrics=state.get("metrics") or MetricsFindings(status="skipped"),
        report=state.get("report")
        or ResearchReport(
            ticker=ticker,
            recommendation="Pending",
            justification="Graph did not produce a report.",
            company_overview="",
            financial_health="",
        ),
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
    duration_ms: float | None = None
    cost_usd: float | None = None
    created_at: datetime


class HistoryResponse(BaseModel):
    ticker: str
    runs: list[HistoryEntry]


# ----- POST /research/ask  (conversational follow-up) -----


class ChatTurn(BaseModel):
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    ticker: str
    question: str = Field(min_length=2, max_length=2000)
    context: ResearchResponse | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class AskResponse(BaseModel):
    answer: str
    cost_usd: float
    request_id: str


_ASK_SYSTEM = """You are Verdict's analyst assistant. The user has already
run a multi-agent research report on a public stock. You receive that report
(SEC filing extracts, recent news sentiment, financial metrics, and a Buy/Hold/Sell
recommendation) as JSON, plus the user's follow-up question.

Answer in 2-6 sentences, conversational tone, plain English.

Hard rules:
  • Ground every claim in the JSON context. If something isn't in the context,
    say so plainly — never invent numbers, headlines, or filings.
  • This is not personalized investment advice. If the user asks for a
    prediction or a "should I" decision, frame it as scenario-based reasoning
    using the provided metrics, and add a one-line disclaimer at the end.
  • For "if I invest $X" hypotheticals: estimate using the 52-week range
    midpoint vs current implied price when available, OR cite the recommendation
    and the metrics that drive it. Show your arithmetic briefly. Always note
    that past ranges don't guarantee future returns.
  • Never recommend specific trades, position sizes, or timing.
  • If context is missing/empty, say "I don't have a fresh report for this
    ticker yet — run the research first."
"""


@lru_cache(maxsize=1)
def _ask_client() -> AsyncOpenAI:
    return make_llm_client()


def _llm_error_detail(e: OpenAIError) -> str:
    """Turn a provider SDK error into a clear, actionable message.

    Distinguishes a hard out-of-quota/billing failure (which retrying never
    fixes) from a transient rate limit — the SDK reports both as
    RateLimitError, which is what made the original failure look like a
    temporary "try again" glitch.
    """
    msg = str(getattr(e, "message", "") or e).lower()
    if any(s in msg for s in ("insufficient_quota", "exceeded your current quota", "billing")):
        return (
            "The AI provider rejected the request: this account is out of "
            "quota/credits. Add billing/credits or switch to a free provider "
            "(e.g. a Google Gemini key). Retrying won't help until then."
        )
    return f"LLM call failed ({type(e).__name__})"


@router.post("/ask", response_model=AskResponse)
@limiter.limit(lambda: get_settings().rate_limit_research)
async def ask(request: Request, body: AskRequest) -> AskResponse:
    ticker = _validate_ticker(body.ticker)
    tracker = start_tracking()
    rid = get_request_id()

    settings = get_settings()
    # Catch missing/placeholder keys early so we return a clean 503 instead of
    # bouncing off the provider SDK. Provider-agnostic: works for an OpenAI key
    # (sk-...) or a Gemini key (AIza...) via LLM_API_KEY.
    if not llm_key_configured(settings.resolved_llm_key):
        raise HTTPException(
            status_code=503,
            detail=(
                "No LLM API key configured. Set LLM_API_KEY (or OPENAI_API_KEY) "
                "in the backend .env and restart. For free Google Gemini, also "
                "set LLM_BASE_URL to its OpenAI-compatible endpoint."
            ),
        )

    grounding: dict[str, Any] = {"ticker": ticker}
    if body.context is not None:
        grounding["report"] = body.context.model_dump()
    else:
        grounding["report"] = None

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _ASK_SYSTEM},
        {
            "role": "user",
            "content": (
                "RESEARCH CONTEXT (JSON):\n"
                + json.dumps(grounding, default=str)
            ),
        },
    ]
    for turn in body.history[-10:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": body.question.strip()})

    try:
        resp = await _ask_client().chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.3,
            max_tokens=500,
        )
    except OpenAIError as e:
        log.exception("ask_llm_failed", extra={"error_type": type(e).__name__})
        raise HTTPException(
            status_code=502,
            detail=_llm_error_detail(e),
        ) from e

    record_chat(settings.llm_model, resp)
    answer = (resp.choices[0].message.content or "").strip() or (
        "I couldn't generate a response. Try rephrasing your question."
    )
    log.info(
        "ask_completed",
        extra={"ticker": ticker, "cost_usd": tracker.total_usd},
    )
    return AskResponse(answer=answer, cost_usd=tracker.total_usd, request_id=rid)


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

    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            run_research(ticker),
            timeout=get_settings().request_timeout_seconds,
        )
    except TimeoutError as e:
        log.warning("research_timeout", extra={"ticker": ticker})
        raise HTTPException(status_code=504, detail="Research timed out") from e
    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    cost_payload = tracker.to_dict()
    response.headers["x-cost-usd"] = f"{tracker.total_usd:.6f}"
    response.headers["x-duration-ms"] = f"{duration_ms:.2f}"

    run = await save_run(
        session,
        ticker=ticker,
        recommendation=result.report.recommendation,
        justification=result.report.justification,
        sentiment_score=result.news.sentiment_score,
        payload=result.model_dump(),
        duration_ms=duration_ms,
        cost_usd=tracker.total_usd,
        request_id=rid,
    )
    log.info(
        "research_completed",
        extra={
            "ticker": ticker,
            "recommendation": result.report.recommendation,
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

async def _sse_stream(ticker: str, tracker: CostTracker, rid: str):
    """Run the graph via astream() and yield SSE events for each node update."""
    graph = get_graph()
    started = time.perf_counter()

    yield {
        "event": "started",
        "data": json.dumps({"ticker": ticker, "request_id": rid}),
    }

    final_state: dict = {}
    try:
        async for chunk in graph.astream({"ticker": ticker}):
            # `chunk` is {node_name: partial_state}
            for node_name, partial in chunk.items():
                final_state.update(partial)
                yield {
                    "event": "node_completed",
                    "data": json.dumps(
                        {"node": node_name, "payload": _serializable(partial)},
                        default=str,
                    ),
                }
    except Exception as e:  # noqa: BLE001
        log.exception("research_stream_failed", extra={"ticker": ticker})
        yield {
            "event": "error",
            "data": json.dumps({"detail": str(e), "error_type": type(e).__name__}),
        }
        return

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    result = _state_to_response(ticker, final_state)

    # Persist (best-effort; SSE consumer doesn't need to wait).
    persisted_id = None
    try:
        async for session in session_scope():
            run = await save_run(
                session,
                ticker=ticker,
                recommendation=result.report.recommendation,
                justification=result.report.justification,
                sentiment_score=result.news.sentiment_score,
                payload=result.model_dump(),
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
        out[k] = v.model_dump() if hasattr(v, "model_dump") else v
    return out


@router.get("/{ticker}/stream")
@limiter.limit(lambda: get_settings().rate_limit_research)
async def research_stream(request: Request, ticker: str) -> EventSourceResponse:
    ticker = _validate_ticker(ticker)
    tracker = start_tracking()
    rid = get_request_id()
    log.info("research_stream_started", extra={"ticker": ticker})
    return EventSourceResponse(_sse_stream(ticker, tracker, rid))


# ----- GET /research/history/{ticker} -----

@router.get("/history/{ticker}", response_model=HistoryResponse)
async def history(
    ticker: str,
    limit: int = 20,
    session: AsyncSession = Depends(session_scope),
) -> HistoryResponse:
    ticker = _validate_ticker(ticker)
    rows = await list_runs_for_ticker(session, ticker, limit=min(max(limit, 1), 100))
    return HistoryResponse(
        ticker=ticker,
        runs=[
            HistoryEntry(
                id=r.id,
                ticker=r.ticker,
                recommendation=r.recommendation,
                justification=r.justification,
                sentiment_score=r.sentiment_score,
                duration_ms=r.duration_ms,
                cost_usd=r.cost_usd,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )
