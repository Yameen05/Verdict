import type { DebateCase, ResearchResponse } from "./types";

export * from "./types";

export type FilingForm = "10-K" | "10-Q";

export interface IngestResponse {
  ticker: string;
  form: FilingForm;
  accession: string;
  filing_date: string;
  chunks_indexed: number;
}

export interface QueryMatch {
  score: number;
  text: string;
  accession: string;
  form: FilingForm;
  filing_date: string;
  chunk_index: number;
}

export interface QueryResponse {
  ticker: string;
  question: string;
  matches: QueryMatch[];
}

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";
const SSE_MESSAGE_BOUNDARY = /\r?\n\r?\n/;
let csrfToken = "";

function requestHeaders(extra: Record<string, string> = {}): HeadersInit {
  return csrfToken ? { ...extra, "X-CSRF-Token": csrfToken } : extra;
}

export function setCsrfToken(token: string): void {
  csrfToken = token;
}

async function errorFromResponse(res: Response): Promise<Error> {
  const text = await res.text();
  let detail = text;
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; request_id?: unknown };
    if (typeof parsed.detail === "string") {
      detail = parsed.request_id
        ? `${parsed.detail} (request ${String(parsed.request_id)})`
        : parsed.detail;
    }
  } catch {
    // Keep the original response text when it is not JSON.
  }
  return new Error(`${res.status} ${res.statusText}: ${detail}`);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: requestHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await errorFromResponse(res);
  }
  return (await res.json()) as T;
}

export interface AuthUser {
  id: number;
  email: string;
  role: "owner" | "member";
  two_factor_enabled: boolean;
}

export interface InviteEntry {
  id: number;
  note: string;
  status: "pending" | "used" | "expired";
  created_at: string;
  expires_at: string;
  used_by_email: string | null;
  used_at: string | null;
}

export interface InviteCreated {
  id: number;
  code: string; // shown exactly once
  note: string;
  expires_at: string;
}

export interface AuthSession {
  user: AuthUser;
  csrf_token: string;
  requires_2fa_setup: boolean;
}

export interface LoginChallenge {
  requires_2fa: true;
  challenge_token: string;
}

export interface TwoFactorSetup {
  secret: string;
  provisioning_uri: string;
  qr_code_data_uri: string;
}

export interface TwoFactorEnabled extends AuthSession {
  recovery_codes: string[];
}

async function authJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: requestHeaders((init.headers as Record<string, string> | undefined) ?? {}),
  });
  if (!res.ok) throw await errorFromResponse(res);
  return (await res.json()) as T;
}

export const authApi = {
  status: () => authJson<{ bootstrap_required: boolean }>("/auth/status"),
  me: () => authJson<AuthSession>("/auth/me"),
  bootstrap: (
    email: string,
    password: string,
    bootstrapToken: string,
  ) =>
    authJson<AuthSession>("/auth/bootstrap", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Bootstrap-Token": bootstrapToken,
      },
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    authJson<AuthSession | LoginChallenge>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  register: (inviteCode: string, email: string, password: string) =>
    authJson<AuthSession>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invite_code: inviteCode, email, password }),
    }),
  createInvite: (note: string) =>
    authJson<InviteCreated>("/auth/invites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    }),
  listInvites: () => authJson<{ invites: InviteEntry[] }>("/auth/invites"),
  revokeInvite: async (id: number) => {
    const res = await fetch(`${BASE_URL}/auth/invites/${id}`, {
      method: "DELETE",
      credentials: "include",
      headers: requestHeaders(),
    });
    if (!res.ok) throw await errorFromResponse(res);
  },
  verifyTwoFactor: (challengeToken: string, code: string) =>
    authJson<AuthSession>("/auth/2fa/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_token: challengeToken, code }),
    }),
  setupTwoFactor: () =>
    authJson<TwoFactorSetup>("/auth/2fa/setup", { method: "POST" }),
  enableTwoFactor: (code: string) =>
    authJson<TwoFactorEnabled>("/auth/2fa/enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    }),
  logout: async () => {
    const res = await fetch(`${BASE_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: requestHeaders(),
    });
    if (!res.ok && res.status !== 401) throw await errorFromResponse(res);
    csrfToken = "";
  },
};

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

export const api = {
  health: async () => {
    const res = await fetch(`${BASE_URL}/health`, { headers: requestHeaders() });
    return res.ok;
  },

  ingest: (ticker: string, form: FilingForm) =>
    postJson<IngestResponse>("/filings/ingest", { ticker, form }),

  query: (ticker: string, question: string, top_k = 5) =>
    postJson<QueryResponse>("/filings/query", { ticker, question, top_k }),

  ask: (body: AskRequest) => postJson<AskResponse>("/research/ask", body),

  priceHistory: async (
    ticker: string,
    range: PriceRange = "1M",
    interval: PriceInterval = "1D",
  ): Promise<PriceHistoryResponse> => {
    const params = new URLSearchParams({ range, interval });
    const res = await fetch(
      `${BASE_URL}/market/${encodeURIComponent(ticker)}/history?${params}`,
      { headers: requestHeaders(), credentials: "include" },
    );
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as PriceHistoryResponse;
  },

  latestPrice: async (
    ticker: string,
    interval: PriceInterval = "1M",
  ): Promise<LatestPriceResponse> => {
    const params = new URLSearchParams({ interval });
    const res = await fetch(
      `${BASE_URL}/market/${encodeURIComponent(ticker)}/quote?${params}`,
      { headers: requestHeaders(), credentials: "include" },
    );
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as LatestPriceResponse;
  },

  research: async (ticker: string): Promise<ResearchEnvelope> => {
    const res = await fetch(`${BASE_URL}/research/${encodeURIComponent(ticker)}`, {
      method: "POST",
      headers: requestHeaders(),
      credentials: "include",
    });
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as ResearchEnvelope;
  },

  scoreboard: async (limit = 100): Promise<ScoreboardResponse> => {
    const res = await fetch(`${BASE_URL}/research/scoreboard?limit=${limit}`, {
      headers: requestHeaders(),
      credentials: "include",
    });
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as ScoreboardResponse;
  },

  history: async (ticker: string, limit = 20): Promise<HistoryResponse> => {
    const res = await fetch(
      `${BASE_URL}/research/history/${encodeURIComponent(ticker)}?limit=${limit}`,
      { headers: requestHeaders(), credentials: "include" },
    );
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as HistoryResponse;
  },

  backtest: async (limit = 200): Promise<BacktestResponse> => {
    const res = await fetch(`${BASE_URL}/market/backtest?limit=${limit}`, {
      headers: requestHeaders(),
      credentials: "include",
    });
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as BacktestResponse;
  },

  timing: async (ticker: string, horizonDays = 14): Promise<TimingAssessment> => {
    const res = await fetch(
      `${BASE_URL}/market/${encodeURIComponent(ticker)}/timing?horizon=${horizonDays}`,
      { headers: requestHeaders(), credentials: "include" },
    );
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as TimingAssessment;
  },

  ready: async () => {
    const res = await fetch(`${BASE_URL}/health/ready`, {
      headers: requestHeaders(),
      credentials: "include",
    });
    return { status: res.status, body: (await res.json()) as ReadinessBody };
  },
};

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

export interface BacktestSummary {
  total_runs: number;
  scored: number;
  hits: number;
  immature: number;
  hit_rate: number | null;
  avg_return_pct: number | null;
  by_horizon: BacktestHorizonStat[];
  rule: string;
}

export interface BacktestResponse {
  entries: BacktestEntry[];
  summary: BacktestSummary;
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

// ----- SSE streaming -----

export type DebateStreamEvent =
  | { kind: "debate_case"; stance: "bull" | "bear"; case: DebateCase }
  | {
      kind: "judge_phase";
      phase: "deliberating" | "followup" | "followup_done";
      question?: string;
      reflection?: number;
      chunks?: number;
    };

export type StreamEvent =
  | { event: "started"; data: { ticker: string; request_id: string } }
  | {
      event: "node_completed";
      data: { node: string; payload: Record<string, unknown> };
    }
  | { event: "debate"; data: DebateStreamEvent }
  | {
      event: "ingest";
      data: { phase: "started" | "done" | "failed"; detail: string };
    }
  | {
      event: "completed";
      data: {
        request_id: string;
        duration_ms: number;
        cost: CostBreakdown | Record<string, never>;
        persisted_id: number | null;
        cached?: boolean;
        cache_age_minutes?: number | null;
        result: ResearchResponse;
      };
    }
  | { event: "error"; data: { detail: string; error_type: string } };

/**
 * Stream a research run via SSE.
 * Uses fetch+ReadableStream so we can POST-style configure headers if needed
 * (EventSource is GET-only and we want consistent header handling).
 */
export async function streamResearch(
  ticker: string,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
  fresh = false,
  horizonDays = 14,
): Promise<void> {
  const params = new URLSearchParams({ horizon: String(horizonDays) });
  if (fresh) params.set("fresh", "true");
  const res = await fetch(
    `${BASE_URL}/research/${encodeURIComponent(ticker)}/stream?${params}`,
    {
      headers: requestHeaders({ Accept: "text/event-stream" }),
      credentials: "include",
      signal,
    },
  );
  if (!res.ok || !res.body) {
    throw await errorFromResponse(res);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // SSE allows either LF or CRLF line endings; consume complete messages.
    let match = SSE_MESSAGE_BOUNDARY.exec(buf);
    while (match) {
      const raw = buf.slice(0, match.index);
      buf = buf.slice(match.index + match[0].length);
      const parsed = parseSseMessage(raw);
      if (parsed) onEvent(parsed);
      match = SSE_MESSAGE_BOUNDARY.exec(buf);
    }
  }
}

function parseSseMessage(raw: string): StreamEvent | null {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  let eventName = "message";
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) return null;
  try {
    const data = JSON.parse(dataLines.join("\n"));
    return { event: eventName as StreamEvent["event"], data } as StreamEvent;
  } catch {
    return null;
  }
}
