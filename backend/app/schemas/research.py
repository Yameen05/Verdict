from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.failure import FailureInfo
from app.services.assessment import assessment_failed, prediction_kind
from app.services.failures import normalize_failure
from app.services.signals.types import (
    AnalystRatings,
    Fundamentals,
    MacroRegime,
    QuoteSignal,
    RetailSentiment,
)

AgentStatus = Literal["ok", "skipped", "not_implemented", "error"]


class SECFinding(BaseModel):
    question: str
    answer: str
    source_chunks: int = Field(description="How many retrieved chunks were used")


class SECFindings(BaseModel):
    status: AgentStatus
    findings: list[SECFinding] = Field(default_factory=list)
    accession: str | None = None
    error: str | None = None
    failure: FailureInfo | None = None


class Headline(BaseModel):
    title: str
    source: str = ""
    published_at: str = ""
    url: str = ""
    score: float | None = Field(default=None, ge=-1.0, le=1.0)


class NewsFindings(BaseModel):
    status: AgentStatus
    sentiment_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    summary: str | None = None
    article_count: int = 0
    top_headlines: list[Headline] = Field(default_factory=list)
    error: str | None = None
    failure: FailureInfo | None = None


class MetricsFindings(BaseModel):
    status: AgentStatus
    revenue: float | None = None
    eps: float | None = None
    pe_ratio: float | None = None
    profit_margin: float | None = None
    debt_to_equity: float | None = None
    week_52_low: float | None = None
    week_52_high: float | None = None
    current_price: float | None = None
    # --- holding-period stats from one year of daily closes ---
    horizon_days: int | None = None
    recent_return_pct: float | None = None  # move over the most recent window
    typical_swing_pct: float | None = None  # ±1 std-dev of rolling window returns
    best_window_pct: float | None = None
    worst_window_pct: float | None = None
    error: str | None = None
    failure: FailureInfo | None = None


class InsiderTransaction(BaseModel):
    insider: str
    role: str | None = None
    date: str = ""
    kind: Literal["buy", "sell", "other"] = "other"
    shares: float | None = None
    value_usd: float | None = None


class InsiderFindings(BaseModel):
    status: AgentStatus
    transactions: list[InsiderTransaction] = Field(default_factory=list)
    buy_count: int = 0
    sell_count: int = 0
    summary: str | None = None
    error: str | None = None
    failure: FailureInfo | None = None


class SignalFindings(BaseModel):
    status: AgentStatus
    analyst: AnalystRatings | None = None
    retail: RetailSentiment | None = None
    macro: MacroRegime | None = None
    fundamentals: Fundamentals | None = None
    quotes: list[QuoteSignal] = Field(default_factory=list)
    earnings_days: int | None = None
    sources_used: list[str] = Field(default_factory=list)
    sources_available: list[str] = Field(default_factory=list)
    error: str | None = None
    failure: FailureInfo | None = None


class EvidenceItem(BaseModel):
    """One citable fact collected by an agent. Referenced by id from arguments."""

    id: str  # e.g. "sec:0", "news:h2", "metrics:pe", "insider:net"
    source: Literal["sec", "news", "metrics", "insider", "signals"]
    label: str
    content: str
    url: str | None = None


class Argument(BaseModel):
    claim: str
    evidence: list[str] = Field(default_factory=list)  # EvidenceItem ids


class DebateCase(BaseModel):
    stance: Literal["bull", "bear"]
    status: AgentStatus = "ok"
    thesis: str = ""
    arguments: list[Argument] = Field(default_factory=list)
    error: str | None = None
    failure: FailureInfo | None = None


class DimensionScores(BaseModel):
    """Judge-assigned 0-10 scores; None when the evidence didn't cover it."""

    valuation: float | None = Field(default=None, ge=0, le=10)
    growth: float | None = Field(default=None, ge=0, le=10)
    profitability: float | None = Field(default=None, ge=0, le=10)
    balance_sheet: float | None = Field(default=None, ge=0, le=10)
    sentiment: float | None = Field(default=None, ge=0, le=10)


class ResearchReport(BaseModel):
    ticker: str
    recommendation: Literal["Buy", "Hold", "Sell", "Pending", "Failed"] = "Pending"
    justification: str
    company_overview: str
    financial_health: str
    key_risks: list[str] = Field(default_factory=list)
    news_summary: str | None = None
    # --- verdict extensions (all optional so pre-debate stored runs still parse) ---
    confidence: int | None = Field(default=None, ge=0, le=100, description="Uncalibrated AI evidence assessment score; not verified odds of profit or guaranteed accuracy")
    scores: DimensionScores | None = None
    falsifiers: list[str] = Field(default_factory=list)
    dissent: str | None = None  # strongest opposing argument the judge overruled
    citations: list[Argument] = Field(default_factory=list)
    delta_summary: str | None = None  # what changed vs the prior stored run
    # --- casual-friendly extensions ---
    horizon_days: int | None = None  # holding period this verdict was framed for
    horizon_outlook: str | None = None  # what could move the price in that window
    simple_summary: str | None = None  # jargon-free 2-3 sentence version
    # Known failed execution, including legacy deterministic fallback records.
    # Failed assessments keep collected facts but carry no prediction or score.
    prediction_kind: Literal["ai", "partial_ai", "rules_based", "none"] | None = None
    analysis_warning: str | None = None
    assessment_status: Literal["complete", "incomplete", "failed"] = "complete"
    degraded: bool = False
    failures: list[FailureInfo] = Field(default_factory=list)

    def fail_assessment(self, *, incomplete: bool = False):
        issued = (
            incomplete
            and self.recommendation in {"Buy", "Hold", "Sell"}
            and self.prediction_kind != "none"
        )
        self.assessment_status = "incomplete" if issued else "failed"
        self.degraded = True
        if issued:
            self.prediction_kind = (
                "rules_based" if self.prediction_kind == "rules_based" else "partial_ai"
            )
        else:
            self.prediction_kind = "none"
            self.recommendation = "Failed"
        self.confidence = None
        self.scores = None
        self.dissent = None
        self.delta_summary = None
        self.horizon_outlook = None
        causes = " ".join(
            dict.fromkeys(f"{f.stage or 'AI review'}: {f.message}" for f in self.failures)
        )
        reason = (
            causes or "A required research step could not finish. Its exact cause was not recorded."
        )
        self.analysis_warning = reason
        if issued:
            self.analysis_warning = f"Analysis incomplete. {reason} The originally issued prediction remains tracked; confidence was not assessed."
        else:
            self.justification = f"Failed to assess. {reason} No usable prediction was issued."
            self.simple_summary = self.justification
        return self

    @model_validator(mode="after")
    def enforce_assessment(self):
        self.prediction_kind = prediction_kind({"report": self.model_dump()})
        if self.prediction_kind == "none" or assessment_failed({"report": self.model_dump()}):
            if not self.failures:
                failure = normalize_failure(RuntimeError(self.justification), stage="final review")
                if failure.kind != "unknown":
                    self.failures = [failure]
            return self.fail_assessment(incomplete=self.prediction_kind != "none")
        return self


class ResearchResponse(BaseModel):
    ticker: str
    sec: SECFindings
    news: NewsFindings
    metrics: MetricsFindings
    report: ResearchReport
    insider: InsiderFindings = Field(default_factory=lambda: InsiderFindings(status="skipped"))
    signals: SignalFindings = Field(default_factory=lambda: SignalFindings(status="skipped"))
    bull: DebateCase | None = None
    bear: DebateCase | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_source_execution(self):
        if assessment_failed(self.model_dump()):
            for name, source in (
                ("filing review", self.sec),
                ("news review", self.news),
                ("financial review", self.metrics),
                ("insider review", self.insider),
                ("market signals", self.signals),
                ("positive case", self.bull),
                ("negative case", self.bear),
            ):
                if source is not None and source.status == "error":
                    source.failure = source.failure or normalize_failure(
                        RuntimeError(source.error or ""), stage=name
                    )
                    source.error = source.failure.message
            failures = [
                source.failure
                for source in (
                    self.sec,
                    self.news,
                    self.metrics,
                    self.insider,
                    self.signals,
                    self.bull,
                    self.bear,
                )
                if source is not None and source.failure
            ]
            self.report.failures = list(
                {f.model_dump_json(): f for f in [*self.report.failures, *failures]}.values()
            )
            self.report.fail_assessment(incomplete=self.report.prediction_kind != "none")
        return self
