from typing import Literal

from pydantic import BaseModel, Field

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


class EvidenceItem(BaseModel):
    """One citable fact collected by an agent. Referenced by id from arguments."""

    id: str  # e.g. "sec:0", "news:h2", "metrics:pe", "insider:net"
    source: Literal["sec", "news", "metrics", "insider"]
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


class DimensionScores(BaseModel):
    """Judge-assigned 0-10 scores; None when the evidence didn't cover it."""

    valuation: float | None = Field(default=None, ge=0, le=10)
    growth: float | None = Field(default=None, ge=0, le=10)
    profitability: float | None = Field(default=None, ge=0, le=10)
    balance_sheet: float | None = Field(default=None, ge=0, le=10)
    sentiment: float | None = Field(default=None, ge=0, le=10)


class ResearchReport(BaseModel):
    ticker: str
    recommendation: Literal["Buy", "Hold", "Sell", "Pending"] = "Pending"
    justification: str
    company_overview: str
    financial_health: str
    key_risks: list[str] = Field(default_factory=list)
    news_summary: str | None = None
    # --- verdict extensions (all optional so pre-debate stored runs still parse) ---
    confidence: int | None = Field(default=None, ge=0, le=100)
    scores: DimensionScores | None = None
    falsifiers: list[str] = Field(default_factory=list)
    dissent: str | None = None  # strongest opposing argument the judge overruled
    citations: list[Argument] = Field(default_factory=list)
    delta_summary: str | None = None  # what changed vs the prior stored run
    # --- casual-friendly extensions ---
    horizon_days: int | None = None  # holding period this verdict was framed for
    horizon_outlook: str | None = None  # what could move the price in that window
    simple_summary: str | None = None  # jargon-free 2-3 sentence version


class ResearchResponse(BaseModel):
    ticker: str
    sec: SECFindings
    news: NewsFindings
    metrics: MetricsFindings
    report: ResearchReport
    insider: InsiderFindings = Field(
        default_factory=lambda: InsiderFindings(status="skipped")
    )
    bull: DebateCase | None = None
    bear: DebateCase | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
