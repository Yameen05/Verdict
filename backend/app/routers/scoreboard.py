"""Track record: open calls stay open until their holding-period deadline."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.db import ResearchRun, list_recent_runs, session_scope
from app.schemas.research import ResearchResponse
from app.services.assessment import assessment_failed
from app.services.backtest import GRADING_RULE, BacktestEntry
from app.services.track_record import grade_runs

router = APIRouter()


class ScoreboardEntry(BacktestEntry):
    outcome: Literal["hit", "miss", "in_progress", "awaiting_price", "unscored", "failed"] = (
        "unscored"
    )


class ScoreboardSummary(BaseModel):
    total_runs: int = 0
    scored: int = 0
    hits: int = 0
    in_progress: int = 0
    awaiting_price: int = 0
    unscored: int = 0
    failed: int = 0
    by_prediction_kind: dict[str, dict[str, int | float | None]] = Field(default_factory=dict)
    hit_rate: float | None = None
    avg_return_buy_pct: float | None = None
    rule: str = GRADING_RULE


class ScoreboardResponse(BaseModel):
    entries: list[ScoreboardEntry] = Field(default_factory=list)
    summary: ScoreboardSummary
    server_time: datetime


class ScoreboardDetail(BaseModel):
    entry: ScoreboardEntry
    justification: str
    duration_ms: float | None
    cost_usd: float | None
    request_id: str | None
    result: ResearchResponse | None
    payload: dict
    original_prediction: dict = Field(default_factory=dict)
    rule: str = GRADING_RULE


def _entry(graded: BacktestEntry) -> ScoreboardEntry:
    data = graded.model_dump()
    if graded.outcome == "immature":
        data["outcome"] = "in_progress"
    elif graded.outcome == "unscored" and graded.recommendation == "Failed":
        data["outcome"] = "failed"
    elif graded.outcome == "unscored" and graded.status_reason.startswith("Waiting"):
        data["outcome"] = "awaiting_price"
    return ScoreboardEntry(**data)


@router.get("/scoreboard", response_model=ScoreboardResponse)
async def scoreboard(
    request: Request,
    limit: int = 100,
    session: AsyncSession = Depends(session_scope),
) -> ScoreboardResponse:
    # Research is communal, as are the original report and its final grade.
    rows = await list_recent_runs(session, limit=min(max(limit, 1), 500))
    now = datetime.now(UTC)
    entries = [_entry(e) for e in await grade_runs(session, rows, now=now)]
    finished = [e for e in entries if e.outcome in {"hit", "miss"}]
    buys = [e.return_pct for e in finished if e.recommendation == "Buy"]
    hits = sum(e.outcome == "hit" for e in finished)
    by_kind = {}
    for kind in ("ai", "partial_ai", "rules_based"):
        group = [e for e in entries if e.prediction_kind == kind and e.tracking_eligible]
        graded = [e for e in group if e.outcome in {"hit", "miss"}]
        count_hits = sum(e.outcome == "hit" for e in graded)
        by_kind[kind] = {
            "total": len(group),
            "scored": len(graded),
            "hits": count_hits,
            "hit_rate": count_hits / len(graded) if graded else None,
        }
    summary = ScoreboardSummary(
        total_runs=len(entries),
        by_prediction_kind=by_kind,
        scored=len(finished),
        hits=hits,
        in_progress=sum(e.outcome == "in_progress" for e in entries),
        awaiting_price=sum(e.outcome == "awaiting_price" for e in entries),
        unscored=sum(e.outcome == "unscored" for e in entries),
        failed=sum(e.outcome == "failed" for e in entries),
        hit_rate=round(hits / len(finished), 4) if finished else None,
        avg_return_buy_pct=round(sum(buys) / len(buys), 2) if buys else None,
    )
    return ScoreboardResponse(entries=entries, summary=summary, server_time=now)


@router.get("/scoreboard/{run_id}", response_model=ScoreboardDetail)
async def scoreboard_detail(
    run_id: int,
    session: AsyncSession = Depends(session_scope),
) -> ScoreboardDetail:
    row = await session.get(ResearchRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    entry = _entry((await grade_runs(session, [row]))[0])
    try:
        result = ResearchResponse.model_validate(row.payload)
    except (ValidationError, TypeError):
        result = None  # Legacy/incomplete payloads still expose all saved data.
    return ScoreboardDetail(
        original_prediction={
            "recommendation": row.recommendation,
            "recorded_confidence_snapshot": row.confidence,
            "horizon_days": row.horizon_days,
            "issued_at": row.created_at.isoformat(),
            "issue_price": row.price_at_run,
            "model": row.llm_model,
        },
        entry=entry,
        justification=result.report.justification
        if result
        else (
            "Failed to assess. No usable prediction was issued."
            if entry.prediction_kind == "none"
            else row.justification
        ),
        duration_ms=row.duration_ms,
        cost_usd=row.cost_usd,
        request_id=row.request_id,
        result=result,
        payload=result.model_dump() if result and assessment_failed(row.payload) else row.payload,
    )
