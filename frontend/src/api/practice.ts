import { deleteJson, getJson, postJson } from "./http";

export type Template = "breakout" | "pullback" | "rsi_recovery";
export interface StrategyRules {
  name: string;
  template: Template;
  lookback: number;
  volume_multiple: number;
  tolerance_pct: number;
  rsi_threshold: number;
}
export interface Strategy extends StrategyRules {
  id: number;
}
export interface RuleCheck {
  label: string;
  passed: boolean;
  explanation: string;
  summary?: string;
}
export interface Evaluation {
  matched: boolean;
  rules_passed: number;
  rules_total: number;
  checks: RuleCheck[];
  as_of: string;
  close: number;
}
export interface Scan {
  strategy: Strategy;
  universe: "liquid" | "watchlist";
  tickers: string[];
  scanned_at: string;
  results: Array<Evaluation & { ticker: string }>;
  skipped: Array<{ ticker: string; reason: string }>;
  data_note: string;
}
export interface StrategyContext {
  ticker: string;
  strategy: Strategy;
  evaluation: Evaluation;
  entry_price: number;
  data_note: string;
}
export interface Quote extends StrategyContext {
  id: string;
  expires_at: string;
}
export interface Plan {
  stop: number;
  target: number;
  thesis: string;
  risk_usd: number;
  reward_usd: number;
}
export interface Trade {
  id: number;
  ticker: string;
  quantity: number;
  entry_price: number;
  exit_price: number | null;
  opened_at: string;
  closed_at: string | null;
  exit_as_of: string | null;
  realized_pnl: number | null;
  context: StrategyContext & { plan: Plan };
  notes: string;
}
export interface Account {
  starting_cash: number;
  cash: number;
  open_cost: number;
  market_value: number | null;
  equity: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
  trades: Trade[];
  marks: Record<string, { price?: number; as_of?: string; reason?: string }>;
  data_note: string;
}
export interface StrategyList {
  strategies: Strategy[];
  templates: Array<{
    template: Template;
    name: string;
    lesson: string;
    why: string;
  }>;
  liquid_universe: string[];
  data_note: string;
}
export const practiceApi = {
  strategies: () => getJson<StrategyList>("/me/strategies"),
  save: (body: StrategyRules, id?: number) =>
    postJson<Strategy>(`/me/strategies${id ? `/${id}` : ""}`, body),
  remove: (id: number) => deleteJson(`/me/strategies/${id}`),
  scan: (id: number, universe: Scan["universe"]) =>
    postJson<Scan>(`/me/strategies/${id}/scan`, { universe }),
  quote: (strategy_id: number, ticker: string) =>
    postJson<Quote>("/me/practice/quote", { strategy_id, ticker }),
  account: () => getJson<Account>("/me/practice"),
  place: (body: {
    quote_id: string;
    quantity: number;
    stop: number;
    target: number;
    thesis: string;
  }) => postJson<Trade>("/me/practice/trades", body),
  close: (id: number) => postJson<Trade>(`/me/practice/trades/${id}/close`, {}),
  notes: (id: number, notes: string) =>
    postJson<Trade>(`/me/practice/trades/${id}/notes`, { notes }),
};
