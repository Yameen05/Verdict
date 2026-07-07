import { useEffect, useRef, useState } from "react";
import { StockPicker, POPULAR_STOCKS } from "./components/StockPicker";
import { QueryResultPanel } from "./components/QueryResult";
import { ReportPanel } from "./components/ReportPanel";
import { AgentProgress, type AgentKey, type AgentState } from "./components/AgentProgress";
import { HistoryPanel } from "./components/HistoryPanel";
import { WelcomeHero } from "./components/WelcomeHero";
import { ChatPanel } from "./components/ChatPanel";
import { VerdictCard } from "./components/VerdictCard";
import { DebatePanel } from "./components/DebatePanel";
import { EvidencePanel } from "./components/EvidencePanel";
import { ScoreboardPanel } from "./components/ScoreboardPanel";
import { WatchlistBar } from "./components/WatchlistBar";
import { downloadReportMarkdown } from "./lib/exportMarkdown";
import {
  api,
  streamResearch,
  type DebateCase,
  type EvidenceItem,
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
  insider_agent: { status: "idle" },
  bull_agent: { status: "idle" },
  bear_agent: { status: "idle" },
  judge: { status: "idle" },
};

function companyName(ticker: string): string {
  return POPULAR_STOCKS.find((s) => s.ticker === ticker)?.name ?? ticker;
}

function summarizePayload(payload: Record<string, unknown>): string {
  for (const k of ["sec", "news", "metrics", "insider", "bull", "bear", "report"]) {
    const v = payload[k] as Record<string, unknown> | undefined;
    if (v && typeof v === "object") {
      const stat =
        (v.recommendation as string | undefined) ?? (v.status as string | undefined);
      if (stat) return String(stat);
    }
  }
  return "done";
}

export default function App({
  userEmail,
  onLogout,
}: {
  userEmail: string;
  onLogout: () => Promise<void>;
}) {
  const [tab, setTab] = useState<"research" | "scoreboard">("research");
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
  // Live debate state — filled progressively over the SSE custom stream.
  const [liveBull, setLiveBull] = useState<DebateCase | null>(null);
  const [liveBear, setLiveBear] = useState<DebateCase | null>(null);
  const [liveEvidence, setLiveEvidence] = useState<EvidenceItem[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api
      .ready()
      .then(({ body }) => setReadiness(body))
      .catch(() => setReadiness(null));
  }, []);

  function setAgent(key: AgentKey, state: AgentState) {
    setAgents((s) => ({ ...s, [key]: state }));
  }

  function resetRun() {
    setResearch(null);
    setMeta(null);
    setLiveBull(null);
    setLiveBear(null);
    setLiveEvidence([]);
    setAgents({
      ...INITIAL_AGENT_STATES,
      sec_agent: { status: "running" },
      news_agent: { status: "running" },
      metrics_agent: { status: "running" },
      insider_agent: { status: "running" },
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
    setStatus(`Convening the trial for ${ticker}…`);
    resetRun();

    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;

    try {
      await streamResearch(
        ticker,
        (e) => {
          if (e.event === "node_completed") {
            const node = e.data.node;
            const payload = e.data.payload;
            if (node === "build_evidence") {
              const ev = payload.evidence as EvidenceItem[] | undefined;
              if (ev) setLiveEvidence(ev);
              setAgent("bull_agent", { status: "running" });
              setAgent("bear_agent", { status: "running" });
              setStatus("Evidence ledger built — advocates are arguing…");
              return;
            }
            if (node === "followup") {
              setAgent("judge", { status: "running", summary: "reviewing new evidence" });
              const ev = payload.evidence as EvidenceItem[] | undefined;
              if (ev) setLiveEvidence(ev);
              return;
            }
            if (node === "judge") {
              if (payload.followup_question) {
                setAgent("judge", {
                  status: "running",
                  summary: "requested more filing evidence",
                });
                return;
              }
              const report = payload.report as { recommendation?: string } | undefined;
              setAgent("judge", {
                status: "done",
                summary: report?.recommendation ?? "done",
              });
              return;
            }
            setAgent(node as AgentKey, {
              status: "done",
              summary: summarizePayload(payload),
            });
          } else if (e.event === "debate") {
            const d = e.data;
            if (d.kind === "debate_case") {
              if (d.stance === "bull") setLiveBull(d.case);
              else setLiveBear(d.case);
              setAgent(d.stance === "bull" ? "bull_agent" : "bear_agent", {
                status: d.case.status === "ok" ? "done" : "error",
                summary: d.case.status === "ok" ? "case filed" : d.case.status,
              });
            } else if (d.kind === "judge_phase") {
              if (d.phase === "deliberating") {
                setAgent("judge", { status: "running", summary: "weighing both cases" });
                setStatus("Both cases filed — the judge is deliberating…");
              } else if (d.phase === "followup" && d.question) {
                setStatus(`Judge requested more evidence: “${d.question}”`);
              }
            }
          } else if (e.event === "completed") {
            setResearch(e.data.result);
            setMeta({ duration_ms: e.data.duration_ms, cost_usd: e.data.cost.total_usd });
            setStatus(
              `Verdict: ${e.data.result.report.recommendation}` +
                (e.data.result.report.confidence !== null
                  ? ` (${e.data.result.report.confidence}/100)`
                  : "") +
                ` · ${(e.data.duration_ms / 1000).toFixed(1)}s · $${e.data.cost.total_usd.toFixed(4)}`,
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

  const showDebate = busy || research !== null;
  const debateBull = research?.bull ?? liveBull;
  const debateBear = research?.bear ?? liveBear;
  const debateEvidence = research?.evidence ?? liveEvidence;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <nav className="sticky top-0 z-10 border-b border-slate-900 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-indigo-500 to-cyan-500 text-xs font-bold text-white">
                V
              </span>
              <span className="font-semibold tracking-tight">Verdict</span>
            </div>
            <div className="flex rounded-lg border border-slate-800 bg-slate-900/60 p-0.5 text-xs">
              {(["research", "scoreboard"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`rounded-md px-3 py-1.5 font-medium capitalize transition ${
                    tab === t ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
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
        {tab === "scoreboard" ? (
          <ScoreboardPanel refreshKey={historyRefresh} />
        ) : (
          <>
            {!research && !busy && <WelcomeHero />}

            <WatchlistBar ticker={ticker} onSelect={setTicker} />

            <section className="space-y-6 rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
              <StockPicker
                ticker={ticker}
                setTicker={setTicker}
                form={form}
                setForm={setForm}
                onIngest={onIngest}
                disabled={busy}
              />

              <div className="border-t border-slate-800 pt-5">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={onResearchStream}
                    disabled={busy}
                    className="rounded-md bg-gradient-to-r from-indigo-600 to-cyan-600 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-900/30 transition hover:from-indigo-500 hover:to-cyan-500 disabled:opacity-50"
                  >
                    Put {ticker} on trial →
                  </button>
                  {busy && (
                    <button
                      onClick={onCancel}
                      className="rounded-md border border-rose-700 px-4 py-2 text-sm font-medium text-rose-300 hover:bg-rose-900/30"
                    >
                      Cancel
                    </button>
                  )}
                  <span className="text-xs text-slate-500">
                    Four evidence agents → bull vs bear advocates → the judge’s verdict, streamed live.
                  </span>
                </div>

                <div className="mt-4">
                  <AgentProgress states={agents} />
                </div>

                {status && <p className="mt-3 text-xs text-slate-400">{status}</p>}

                <details className="mt-4 rounded-md border border-slate-800 bg-slate-950/40">
                  <summary className="cursor-pointer select-none px-3 py-2 text-xs uppercase tracking-wider text-slate-400 hover:text-slate-200">
                    Ad-hoc filing search
                  </summary>
                  <div className="space-y-2 px-3 pb-3">
                    <textarea
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      rows={2}
                      className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm placeholder-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <button
                      onClick={onQuery}
                      disabled={busy}
                      className="rounded-md border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
                    >
                      Query filing
                    </button>
                  </div>
                </details>
              </div>
            </section>

            {research && (
              <div className="mt-6">
                <VerdictCard
                  result={research}
                  meta={meta}
                  onExport={() => downloadReportMarkdown(research, meta)}
                />
              </div>
            )}

            {showDebate && (
              <DebatePanel
                bull={debateBull}
                bear={debateBear}
                evidence={debateEvidence}
                live={busy && !research}
              />
            )}

            <ReportPanel result={research} />
            <EvidencePanel evidence={research?.evidence ?? []} />

            <ChatPanel ticker={ticker} research={research} />

            <QueryResultPanel result={queryResult} />

            <section className="mt-8">
              <h2 className="mb-2 text-sm font-semibold text-slate-200">
                Verdict history for{" "}
                <span className="font-mono text-indigo-300">{ticker}</span>{" "}
                <span className="font-normal text-slate-500">({companyName(ticker)})</span>
              </h2>
              <HistoryPanel ticker={ticker} refreshKey={historyRefresh} />
            </section>
          </>
        )}

        <footer className="mt-12 border-t border-slate-900 pt-6 text-center text-[11px] text-slate-600">
          Verdict is for informational purposes only. Not investment advice. Data from
          SEC EDGAR, NewsAPI, and Yahoo Finance via yfinance.
        </footer>
      </main>
    </div>
  );
}
