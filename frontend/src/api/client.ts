import type {
  AskRequest,
  AskResponse,
  AssetCapabilities,
  BacktestResponse,
  ConfigStatus,
  CostBreakdown,
  DebateCase,
  HistoryResponse,
  LatestPriceResponse,
  PriceInterval,
  PriceRange,
  PriceHistoryResponse,
  ReadinessBody,
  ResearchEnvelope,
  ResearchResponse,
  ReturnRangeResponse,
  ScoreboardResponse,
  ServerAlert,
  ServerPosition,
  TimingAssessment,
} from "./types";
import {
  BASE_URL,
  deleteJson,
  errorFromResponse,
  getJson,
  postJson,
  requestHeaders,
} from "./http";

export * from "./types";
export * from "./auth";
export { setCsrfToken } from "./http";

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

const SSE_MESSAGE_BOUNDARY = /\r?\n\r?\n/;

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

  configStatus: async (): Promise<ConfigStatus> => {
    const res = await fetch(`${BASE_URL}/health/config`, {
      headers: requestHeaders(),
      credentials: "include",
    });
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as ConfigStatus;
  },

  returnRanges: async (ticker: string, amount = 200): Promise<ReturnRangeResponse> => {
    const params = new URLSearchParams({ amount: String(amount) });
    const res = await fetch(
      `${BASE_URL}/market/${encodeURIComponent(ticker)}/ranges?${params}`,
      { headers: requestHeaders(), credentials: "include" },
    );
    if (!res.ok) {
      throw await errorFromResponse(res);
    }
    return (await res.json()) as ReturnRangeResponse;
  },

  capabilities: async (ticker: string): Promise<AssetCapabilities> =>
    getJson<AssetCapabilities>(`/market/${encodeURIComponent(ticker)}/capabilities`),
};

/** Per-user workspace state persisted on the backend (was localStorage). */
export const userStateApi = {
  watchlist: () => getJson<{ tickers: string[] }>("/me/watchlist"),
  addWatchlist: (ticker: string) =>
    postJson<{ tickers: string[] }>("/me/watchlist", { ticker }),
  removeWatchlist: (ticker: string) =>
    deleteJson<{ tickers: string[] }>(`/me/watchlist/${encodeURIComponent(ticker)}`),

  position: (ticker: string) =>
    getJson<{ position: ServerPosition | null }>(
      `/me/positions/${encodeURIComponent(ticker)}`,
    ),
  savePosition: (position: ServerPosition) =>
    postJson<{ position: ServerPosition }>("/me/positions", position),
  deletePosition: (ticker: string) =>
    deleteJson<{ position: null }>(`/me/positions/${encodeURIComponent(ticker)}`),

  alerts: (ticker?: string) =>
    getJson<{ alerts: ServerAlert[] }>(
      ticker ? `/me/alerts?ticker=${encodeURIComponent(ticker)}` : "/me/alerts",
    ),
  createAlert: (ticker: string, direction: "above" | "below", price: number) =>
    postJson<{ alert: ServerAlert }>("/me/alerts", { ticker, direction, price }),
  triggerAlert: (id: number) => postJson<{ alert: ServerAlert }>(`/me/alerts/${id}/trigger`, {}),
  deleteAlert: (id: number) => deleteJson<{ ok: boolean }>(`/me/alerts/${id}`),

  levels: (ticker: string) =>
    getJson<{ prices: number[] }>(`/me/levels/${encodeURIComponent(ticker)}`),
  addLevel: (ticker: string, price: number) =>
    postJson<{ prices: number[] }>("/me/levels", { ticker, price }),
  clearLevels: (ticker: string, price?: number) =>
    deleteJson<{ prices: number[] }>(
      `/me/levels/${encodeURIComponent(ticker)}${price !== undefined ? `?price=${price}` : ""}`,
    ),

  verdictWatch: (ticker: string) =>
    getJson<{ recommendation: string | null }>(
      `/me/verdict-watch/${encodeURIComponent(ticker)}`,
    ),
  setVerdictWatch: (ticker: string, recommendation: string) =>
    postJson<{ recommendation: string }>("/me/verdict-watch", { ticker, recommendation }),
};


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
