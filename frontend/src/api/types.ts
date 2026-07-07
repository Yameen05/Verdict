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

export interface EvidenceItem {
  id: string;
  source: "sec" | "news" | "metrics" | "insider";
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
}

export interface ResearchResponse {
  ticker: string;
  sec: SECFindings;
  news: NewsFindings;
  metrics: MetricsFindings;
  insider: InsiderFindings;
  bull: DebateCase | null;
  bear: DebateCase | null;
  evidence: EvidenceItem[];
  report: ResearchReport;
}

