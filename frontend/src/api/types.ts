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

// ----- API payload types (moved from client.ts) -----

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AskRequest {
  ticker: string;
  question: string;
  context: ResearchResponse | null;
  history: ChatTurn[];
}

export interface AskResponse {
  answer: string;
  cost_usd: number;
  request_id: string;
  searched_filing: boolean;
}

export type PriceRange = "1D" | "5D" | "1M" | "3M" | "6M" | "1Y" | "5Y";
export type PriceInterval = "1M" | "5M" | "15M" | "1H" | "1D" | "1W";

export interface PriceBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface PriceHistoryResponse {
  ticker: string;
  range: PriceRange;
  interval: PriceInterval;
  requested_interval: PriceInterval;
  bars: PriceBar[];
}

export interface LatestPriceResponse {
  ticker: string;
  interval: PriceInterval;
  requested_interval: PriceInterval;
  bar: PriceBar;
}

export interface ServerPosition {
  ticker: string;
  amount_usd: number;
  buy_date: string;
  buy_price: number | null;
}

export interface ServerAlert {
  id: number;
  ticker: string;
  direction: "above" | "below";
  price: number;
  triggered: boolean;
  triggered_at: string | null;
  triggered_price: number | null;
  created_at: string;
}

export interface AssetCapabilities {
  ticker: string;
  asset_class: "equity" | "crypto";
  display_name: string | null;
  has_filings: boolean;
  has_insiders: boolean;
  has_earnings: boolean;
  has_analyst_coverage: boolean;
  trades_24_7: boolean;
  note: string | null;
}

export interface CostBreakdown {
  prompt_tokens: number;
  completion_tokens: number;
  embedding_tokens: number;
  total_usd: number;
}

export interface ResearchEnvelope {
  request_id: string;
  duration_ms: number;
  cost: CostBreakdown;
  persisted_id: number | null;
  cached: boolean;
  cache_age_minutes: number | null;
  result: ResearchResponse;
}

export interface HistoryEntry {
  id: number;
  ticker: string;
  recommendation: "Buy" | "Hold" | "Sell" | "Pending";
  justification: string;
  sentiment_score: number | null;
  confidence: number | null;
  price_at_run: number | null;
  duration_ms: number | null;
  cost_usd: number | null;
  created_at: string;
}

export interface ScoreboardEntry {
  id: number;
  ticker: string;
  recommendation: string;
  confidence: number | null;
  created_at: string;
  price_at_run: number | null;
  current_price: number | null;
  return_pct: number | null;
  outcome: "hit" | "miss" | "unscored";
}

export interface ScoreboardSummary {
  total_runs: number;
  scored: number;
  hits: number;
  hit_rate: number | null;
  avg_return_buy_pct: number | null;
  rule: string;
}

export interface ScoreboardResponse {
  entries: ScoreboardEntry[];
  summary: ScoreboardSummary;
}

export type BacktestOutcome = "hit" | "miss" | "immature" | "unscored";

export interface BacktestEntry {
  id: number;
  ticker: string;
  recommendation: string;
  confidence: number | null;
  horizon_days: number;
  created_at: string;
  evaluated_at: string | null;
  price_at_run: number | null;
  price_at_horizon: number | null;
  return_pct: number | null;
  outcome: BacktestOutcome;
}

export interface BacktestHorizonStat {
  horizon_days: number;
  scored: number;
  hits: number;
  hit_rate: number | null;
  avg_return_pct: number | null;
}

export interface ConfidenceBucket {
  label: string;
  scored: number;
  hits: number;
  hit_rate: number | null;
  avg_confidence: number | null;
}

export interface BacktestSummary {
  total_runs: number;
  scored: number;
  hits: number;
  immature: number;
  hit_rate: number | null;
  avg_return_pct: number | null;
  by_horizon: BacktestHorizonStat[];
  by_confidence: ConfidenceBucket[];
  brier_score: number | null;
  rule: string;
}

export interface BacktestResponse {
  entries: BacktestEntry[];
  summary: BacktestSummary;
}

export interface ReturnRangeRow {
  horizon_days: number;
  label: string;
  amount: number;
  likely_low: number | null;
  likely_high: number | null;
  normal_move_pct: number | null;
  recent_return_pct: number | null;
  best_case: number | null;
  best_case_pct: number | null;
  worst_case: number | null;
  worst_case_pct: number | null;
}

export interface ReturnRangeResponse {
  ticker: string;
  amount: number;
  rows: ReturnRangeRow[];
  note: string;
}

export type TimingAction =
  | "buy_now"
  | "accumulate"
  | "wait_pullback"
  | "wait_watch"
  | "avoid";

export interface TimingAssessment {
  ticker: string;
  horizon_days: number;
  action: TimingAction;
  action_label: string;
  confidence: number;
  summary: string;
  rationale: string[];
  risks: string[];
  entry_zone_low: number | null;
  entry_zone_high: number | null;
  technicals: Record<string, unknown>;
  market_signals: Record<string, unknown>;
  headlines: string[];
  as_of: string;
  source: "llm" | "rules";
  disclaimer: string;
}

export interface HistoryResponse {
  ticker: string;
  runs: HistoryEntry[];
}

export interface ReadinessCheck {
  ok: boolean;
  detail: string;
}

export interface ReadinessBody {
  status: "ready" | "degraded";
  checks: Record<string, ReadinessCheck>;
}

export interface ConfigStatus {
  environment: string;
  llm: {
    provider: string;
    model: string;
    configured: boolean;
    rate_limit: string;
  };
  embeddings: {
    model: string;
    configured: boolean;
  };
  sources: {
    newsapi: boolean;
    vectorstore: string;
    signals: Record<string, boolean>;
    signals_cache_seconds: number;
  };
  quotas: {
    research_cache_minutes: number;
    daily_runs_per_user: number;
    daily_runs_global: number;
  };
}

// ----- Day-trade desk -----

export type DayTradeAction = "long" | "short" | "stand_aside";
export type DayTradeVote = "long" | "short" | "neutral";

export interface DayTradeAgentView {
  name: string;
  vote: DayTradeVote;
  score: number;
  reasons: string[];
}

export interface DayTradeSignal {
  ticker: string;
  action: DayTradeAction;
  action_label: string;
  confidence: number;
  session: string;
  session_note: string;
  summary: string;
  entry: number | null;
  stop: number | null;
  target: number | null;
  risk_per_share: number | null;
  risk_reward: number | null;
  rationale: string[];
  risks: string[];
  plan: string[];
  agents: DayTradeAgentView[];
  technicals: Record<string, unknown>;
  headlines: string[];
  as_of: string;
  source: "llm" | "rules";
  disclaimer: string;
}

export interface DayTradeScanRow {
  ticker: string;
  action: DayTradeAction;
  action_label: string;
  confidence: number;
  close: number;
  score: number;
  note: string;
}

export interface DayTradeScanResponse {
  rows: DayTradeScanRow[];
  skipped: string[];
  as_of: string;
  note: string;
}
