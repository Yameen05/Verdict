// Research-domain types shared by the API client and components.

export type AgentStatus = "ok" | "skipped" | "not_implemented" | "error";

export interface SECFinding {
  question: string;
  answer: string;
  source_chunks: number;
}

export interface SECFindings {
  status: AgentStatus;
  findings: SECFinding[];
  accession: string | null;
  error: string | null;
}

export interface Headline {
  title: string;
  source: string;
  published_at: string;
  url: string;
  score: number | null;
}

export interface NewsFindings {
  status: AgentStatus;
  sentiment_score: number | null;
  summary: string | null;
  article_count: number;
  top_headlines: Headline[];
  error: string | null;
}

export interface MetricsFindings {
  status: AgentStatus;
  revenue: number | null;
  eps: number | null;
  pe_ratio: number | null;
  profit_margin: number | null;
  debt_to_equity: number | null;
  week_52_low: number | null;
  week_52_high: number | null;
  current_price: number | null;
  horizon_days: number | null;
  recent_return_pct: number | null;
  typical_swing_pct: number | null;
  best_window_pct: number | null;
  worst_window_pct: number | null;
  error: string | null;
}

export interface InsiderTransaction {
  insider: string;
  role: string | null;
  date: string;
  kind: "buy" | "sell" | "other";
  shares: number | null;
  value_usd: number | null;
}

export interface InsiderFindings {
  status: AgentStatus;
  transactions: InsiderTransaction[];
  buy_count: number;
  sell_count: number;
  summary: string | null;
  error: string | null;
}

export interface AnalystRatings {
  strong_buy: number;
  buy: number;
  hold: number;
  sell: number;
  strong_sell: number;
  period: string | null;
  consensus: string;
  score: number;
  source: string;
}

export interface RetailSentiment {
  bullish: number;
  bearish: number;
  sample: number;
  score: number;
  label: string;
  source: string;
}

export interface MacroRegime {
  fed_funds_pct: number | null;
  cpi_yoy_pct: number | null;
  unemployment_pct: number | null;
  yield_spread_10y_2y: number | null;
  regime: string;
  note: string;
  source: string;
}

export interface Fundamentals {
  pe_ratio: number | null;
  peg_ratio: number | null;
  profit_margin: number | null;
  analyst_target: number | null;
  source: string;
}

export interface QuoteSignal {
  price: number | null;
  change_pct: number | null;
  source: string;
}

export interface SignalFindings {
  status: AgentStatus;
  analyst: AnalystRatings | null;
  retail: RetailSentiment | null;
  macro: MacroRegime | null;
  fundamentals: Fundamentals | null;
  quotes: QuoteSignal[];
  earnings_days: number | null;
  sources_used: string[];
  sources_available: string[];
  error: string | null;
}

export interface EvidenceItem {
  id: string;
  source: "sec" | "news" | "metrics" | "insider" | "signals";
  label: string;
  content: string;
  url: string | null;
}

export interface Argument {
  claim: string;
  evidence: string[];
}

export interface DebateCase {
  stance: "bull" | "bear";
  status: AgentStatus;
  thesis: string;
  arguments: Argument[];
  error: string | null;
}

export interface DimensionScores {
  valuation: number | null;
  growth: number | null;
  profitability: number | null;
  balance_sheet: number | null;
  sentiment: number | null;
}

export interface ResearchReport {
  ticker: string;
  recommendation: "Buy" | "Hold" | "Sell" | "Pending";
  justification: string;
  company_overview: string;
  financial_health: string;
  key_risks: string[];
  news_summary: string | null;
  confidence: number | null;
  scores: DimensionScores | null;
  falsifiers: string[];
  dissent: string | null;
  citations: Argument[];
  delta_summary: string | null;
  horizon_days: number | null;
  horizon_outlook: string | null;
  simple_summary: string | null;
}

export interface ResearchResponse {
  ticker: string;
  sec: SECFindings;
  news: NewsFindings;
  metrics: MetricsFindings;
  insider: InsiderFindings;
  signals: SignalFindings;
  bull: DebateCase | null;
  bear: DebateCase | null;
  evidence: EvidenceItem[];
  report: ResearchReport;
}
