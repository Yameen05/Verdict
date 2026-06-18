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

export interface NewsFindings {
  status: AgentStatus;
  sentiment_score: number | null;
  summary: string | null;
  article_count: number;
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
  error: string | null;
}

export interface ResearchReport {
  ticker: string;
  recommendation: "Buy" | "Hold" | "Sell" | "Pending";
  justification: string;
  company_overview: string;
  financial_health: string;
  key_risks: string[];
  news_summary: string | null;
}

export interface ResearchResponse {
  ticker: string;
  sec: SECFindings;
  news: NewsFindings;
  metrics: MetricsFindings;
  report: ResearchReport;
}

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";
const API_KEY = import.meta.env.VITE_VERDICT_API_KEY?.trim();
const SSE_MESSAGE_BOUNDARY = /\r?\n\r?\n/;

function requestHeaders(extra: Record<string, string> = {}): HeadersInit {
  return API_KEY ? { ...extra, "X-API-Key": API_KEY } : extra;
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
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await errorFromResponse(res);
  }
  return (await res.json()) as T;
}

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

  research: async (ticker: string): Promise<ResearchEnvelope> => {
    const res = await fetch(`${BASE_URL}/research/${encodeURIComponent(ticker)}`, {
      method: "POST",
      headers: requestHeaders(),
    });
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as ResearchEnvelope;
  },

  history: async (ticker: string, limit = 20): Promise<HistoryResponse> => {
    const res = await fetch(
      `${BASE_URL}/research/history/${encodeURIComponent(ticker)}?limit=${limit}`,
      { headers: requestHeaders() },
    );
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as HistoryResponse;
  },

  ready: async () => {
    const res = await fetch(`${BASE_URL}/health/ready`, { headers: requestHeaders() });
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
  result: ResearchResponse;
}

export interface HistoryEntry {
  id: number;
  ticker: string;
  recommendation: "Buy" | "Hold" | "Sell" | "Pending";
  justification: string;
  sentiment_score: number | null;
  duration_ms: number | null;
  cost_usd: number | null;
  created_at: string;
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

export type StreamEvent =
  | { event: "started"; data: { ticker: string; request_id: string } }
  | {
      event: "node_completed";
      data: { node: string; payload: Record<string, unknown> };
    }
  | {
      event: "completed";
      data: {
        request_id: string;
        duration_ms: number;
        cost: CostBreakdown;
        persisted_id: number | null;
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
): Promise<void> {
  const res = await fetch(
    `${BASE_URL}/research/${encodeURIComponent(ticker)}/stream`,
    { headers: requestHeaders({ Accept: "text/event-stream" }), signal },
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
