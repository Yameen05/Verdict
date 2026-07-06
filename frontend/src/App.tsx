import { useEffect, useRef, useState } from "react";
import { StockPicker, POPULAR_STOCKS } from "./components/StockPicker";
import { QueryResultPanel } from "./components/QueryResult";
import { ReportPanel } from "./components/ReportPanel";
import { AgentProgress, type AgentKey, type AgentState } from "./components/AgentProgress";
import { HistoryPanel } from "./components/HistoryPanel";
import { WelcomeHero } from "./components/WelcomeHero";
import { ChatPanel } from "./components/ChatPanel";
import {
  api,
  streamResearch,
  type FilingForm,
  type QueryResponse,
  type ResearchResponse,
  type ReadinessBody,
} from "./api/client";

type AgentStates = Record<AgentKey, AgentState>;

const INITIAL_AGENT_STATES: AgentStates = {
  sec_agent: { status: "idle" },
  news_agent: { status: "idle" },
  metrics_agent: { status: "idle" },
  synthesize: { status: "idle" },
};

function companyName(ticker: string): string {
  return POPULAR_STOCKS.find((s) => s.ticker === ticker)?.name ?? ticker;
}

export default function App({
  userEmail,
  onLogout,
}: {
  userEmail: string;
  onLogout: () => Promise<void>;
}) {
  const [ticker, setTicker] = useState("AAPL");
  const [form, setForm] = useState<FilingForm>("10-K");
  const [question, setQuestion] = useState("What are the principal risks?");
  const [queryResult, setQueryResult] = useState<QueryResponse | null>(null);
  const [research, setResearch] = useState<ResearchResponse | null>(null);
  const [meta, setMeta] = useState<{ duration_ms: number; cost_usd: number } | null>(null);
  const [agents, setAgents] = useState<AgentStates>(INITIAL_AGENT_STATES);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [readiness, setReadiness] = useState<ReadinessBody | null>(null);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api
      .ready()
      .then(({ body }) => setReadiness(body))
      .catch(() => setReadiness(null));
  }, []);

  function resetAgents() {
    setAgents({
      sec_agent: { status: "running" },
      news_agent: { status: "running" },
      metrics_agent: { status: "running" },
      synthesize: { status: "idle" },
    });
  }

  async function onIngest() {
    setBusy(true);
    setStatus(`Ingesting ${form} for ${ticker}…`);
    try {
      const out = await api.ingest(ticker, form);
      setStatus(
        `Indexed ${out.chunks_indexed} chunks · ${out.accession} (${out.filing_date})`,
      );
    } catch (e) {
      setStatus(`Ingest failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onQuery() {
    setBusy(true);
    setStatus("Querying…");
    setQueryResult(null);
    try {
      const out = await api.query(ticker, question, 5);
      setQueryResult(out);
      setStatus(`Returned ${out.matches.length} chunks`);
    } catch (e) {
      setStatus(`Query failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onResearchStream() {
    setBusy(true);
    setStatus(`Streaming research for ${ticker}…`);
    setResearch(null);
    setMeta(null);
    resetAgents();

    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;

    try {
      await streamResearch(
        ticker,
        (e) => {
          if (e.event === "node_completed") {
            const node = e.data.node as AgentKey;
            const payload = e.data.payload;
            let summary = "done";
            for (const k of ["sec", "news", "metrics", "report"]) {
              const v = (payload as Record<string, unknown>)[k] as
                | Record<string, unknown>
                | undefined;
              if (v && typeof v === "object") {
                const stat = (v.status as string) ?? (v.recommendation as string);
                if (stat) summary = String(stat);
              }
            }
            setAgents((s) => ({ ...s, [node]: { status: "done", summary } }));
          } else if (e.event === "completed") {
            setResearch(e.data.result);
            setMeta({ duration_ms: e.data.duration_ms, cost_usd: e.data.cost.total_usd });
            setStatus(
              `Report ready · ${e.data.result.report.recommendation} · ${(
                e.data.duration_ms / 1000
              ).toFixed(1)}s · $${e.data.cost.total_usd.toFixed(4)}`,
            );
            setHistoryRefresh((n) => n + 1);
          } else if (e.event === "error") {
            setStatus(`Research failed: ${e.data.detail}`);
          }
        },
        ctl.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setStatus(`Research failed: ${(e as Error).message}`);
      }
    } finally {
      setBusy(false);
    }
  }

  function onCancel() {
    abortRef.current?.abort();
    setBusy(false);
    setStatus("Cancelled");
  }

  const readinessSummary =
    readiness === null
      ? { color: "text-slate-400", text: "checking…" }
      : readiness.status === "ready"
      ? { color: "text-emerald-400", text: "all systems ready" }
      : {
          color: "text-amber-400",
          text:
            "degraded: " +
            Object.entries(readiness.checks)
              .filter(([, c]) => !c.ok)
              .map(([k]) => k)
              .join(", "),
        };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <nav className="border-b border-slate-900 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-indigo-500 to-cyan-500 text-xs font-bold text-white">
              V
            </span>
            <span className="font-semibold tracking-tight">Verdict</span>
            <span className="hidden text-xs text-slate-500 sm:inline">
              · multi-agent equity research
            </span>
          </div>
          <div className="flex items-center gap-4 text-right text-xs">
            <span className={readinessSummary.color} title="Backend readiness">
              ● {readinessSummary.text}
            </span>
            <span className="hidden text-slate-500 md:inline">{userEmail}</span>
            <button
              type="button"
              onClick={() => void onLogout()}
              className="rounded-md border border-slate-800 px-2.5 py-1.5 text-slate-300 hover:bg-slate-900"
            >
              Sign out
            </button>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <WelcomeHero />

        <section className="space-y-6 rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
          <div>
            <h2 className="text-base font-semibold text-slate-100">
              1 · Choose your stock
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              Pick from the curated list or use the custom field. “Ingest filing” downloads
              and indexes the latest SEC filing — only required for SEC-specific questions.
            </p>
          </div>

          <StockPicker
            ticker={ticker}
            setTicker={setTicker}
            form={form}
            setForm={setForm}
            onIngest={onIngest}
            disabled={busy}
          />

          <div className="border-t border-slate-800 pt-6">
            <h2 className="text-base font-semibold text-slate-100">
              2 · Run the analysis
            </h2>
            <p className="mt-0.5 text-xs text-slate-400">
              Full research runs three agents in parallel and synthesizes a recommendation.
              The ad-hoc query searches only the indexed filing.
            </p>

            <div className="mt-4">
              <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-400">
                Ad-hoc question (SEC filing only)
              </label>
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={2}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm placeholder-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  onClick={onResearchStream}
                  disabled={busy}
                  className="rounded-md bg-gradient-to-r from-indigo-600 to-cyan-600 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-900/30 transition hover:from-indigo-500 hover:to-cyan-500 disabled:opacity-50"
                >
                  Run full research →
                </button>
                <button
                  onClick={onQuery}
                  disabled={busy}
                  className="rounded-md border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
                >
                  Query filing
                </button>
                {busy && (
                  <button
                    onClick={onCancel}
                    className="rounded-md border border-rose-700 px-4 py-2 text-sm font-medium text-rose-300 hover:bg-rose-900/30"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>

            <div className="mt-5">
              <AgentProgress states={agents} />
            </div>

            {status && <p className="mt-3 text-xs text-slate-400">{status}</p>}
            {meta && (
              <p className="text-[11px] text-slate-500">
                run · {(meta.duration_ms / 1000).toFixed(2)}s · $
                {meta.cost_usd.toFixed(4)}
              </p>
            )}
          </div>
        </section>

        <ReportPanel result={research} />

        <ChatPanel ticker={ticker} research={research} />

        <QueryResultPanel result={queryResult} />

        <section className="mt-8">
          <h2 className="mb-2 text-sm font-semibold text-slate-200">
            Recent reports for{" "}
            <span className="font-mono text-indigo-300">{ticker}</span>{" "}
            <span className="font-normal text-slate-500">({companyName(ticker)})</span>
          </h2>
          <HistoryPanel ticker={ticker} refreshKey={historyRefresh} />
        </section>

        <footer className="mt-12 border-t border-slate-900 pt-6 text-center text-[11px] text-slate-600">
          Verdict is for informational purposes only. Not investment advice. Data from
          SEC EDGAR, NewsAPI, and Yahoo Finance via yfinance.
        </footer>
      </main>
    </div>
  );
}
