"""Shared LangGraph state for the research pipeline."""

from __future__ import annotations

from typing import Any, TypedDict

from app.schemas.research import (
    DebateCase,
    EvidenceItem,
    InsiderFindings,
    MetricsFindings,
    NewsFindings,
    ResearchReport,
    SECFindings,
)


class ResearchState(TypedDict, total=False):
    ticker: str
    # Each agent node populates its slot; missing slots are treated as "skipped".
    sec: SECFindings
    news: NewsFindings
    metrics: MetricsFindings
    insider: InsiderFindings
    # Deterministic evidence ledger built after the fetch agents complete.
    evidence: list[EvidenceItem]
    # Adversarial debate slots.
    bull: DebateCase
    bear: DebateCase
    report: ResearchReport
    # Most recent stored run for this ticker (dict with recommendation,
    # justification, created_at) — lets the judge write a delta_summary.
    prior_run: dict[str, Any] | None
    # Reflection loop: judge may request ONE follow-up SEC retrieval.
    followup_question: str | None
    reflection_count: int
