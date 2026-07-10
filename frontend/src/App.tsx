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
import { BacktestPanel } from "./components/BacktestPanel";
import { WatchlistBar } from "./components/WatchlistBar";
import { InvitesPanel } from "./components/InvitesPanel";
import { StockChartPanel } from "./components/StockChartPanel";
import { TimingPanel } from "./components/chart/TimingPanel";
import { ReturnRangePanel } from "./components/ReturnRangePanel";
import { PositionTracker } from "./components/PositionTracker";
import { CalibrationPanel } from "./components/CalibrationPanel";
import { SourceQualityPanel } from "./components/SourceQualityPanel";
import { DisagreementPanel } from "./components/DisagreementPanel";
import { ApiStatusPanel } from "./components/ApiStatusPanel";
import { SmartAlertsPanel } from "./components/SmartAlertsPanel";
import { downloadReportMarkdown } from "./lib/exportMarkdown";
import { migrateLocalStateOnce } from "./lib/migrateLocalState";
import {
  api,
  streamResearch,
  type AssetCapabilities,
  type ConfigStatus,
  type DebateCase,
  type EvidenceItem,
  type FilingForm,
  type QueryResponse,
  type ResearchResponse,
  type ReadinessBody,
  type TimingAssessment,
} from "./api/client";

type AgentStates = Record<AgentKey, AgentState>;
type ThemeMode = "dark" | "light";

const THEME_STORAGE_KEY = "verdict-theme-v2";

const INITIAL_AGENT_STATES: AgentStates = {
  sec_agent: { status: "idle" },
  news_agent: { status: "idle" },
  metrics_agent: { status: "idle" },
  insider_agent: { status: "idle" },
  signals_agent: { status: "idle" },
  bull_agent: { status: "idle" },
  bear_agent: { status: "idle" },
  judge: { status: "idle" },
};

function companyName(ticker: string): string {
  return POPULAR_STOCKS.find((s) => s.ticker === ticker)?.name ?? ticker;
}

function initialTheme(): ThemeMode {
  return window.localStorage.getItem(THEME_STORAGE_KEY) === "light" ? "light" : "dark";
}

// Holding periods the backend accepts; labels avoid jargon on purpose.
const HORIZONS: { days: number; label: string; hint: string }[] = [
  { days: 7, label: "1 week", hint: "quick trade" },
  { days: 14, label: "2 weeks", hint: "short hold" },
  { days: 30, label: "1 month", hint: "" },
  { days: 90, label: "3 months", hint: "" },
  { days: 365, label: "1 year", hint: "52 weeks — the long game" },
];

function summarizePayload(payload: Record<string, unknown>): string {
  for (const k of ["sec", "news", "metrics", "insider", "signals", "bull", "bear", "report"]) {
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
  userRole,
  onLogout,
}: {
  userEmail: string;
  userRole: "owner" | "member";
  onLogout: () => Promise<void>;
}) {
  const [tab, setTab] = useState<"research" | "scoreboard">("research");
  const [ticker, setTicker] = useState("AAPL");
  const [horizonDays, setHorizonDays] = useState(14);
  const [form, setForm] = useState<FilingForm>("10-K");
  const [question, setQuestion] = useState("What are the principal risks?");
  const [queryResult, setQueryResult] = useState<QueryResponse | null>(null);
  const [research, setResearch] = useState<ResearchResponse | null>(null);
  const [meta, setMeta] = useState<{ duration_ms: number; cost_usd: number } | null>(null);
  const [agents, setAgents] = useState<AgentStates>(INITIAL_AGENT_STATES);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [readiness, setReadiness] = useState<ReadinessBody | null>(null);
  const [configStatus, setConfigStatus] = useState<ConfigStatus | null>(null);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [showInvites, setShowInvites] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(initialTheme);
  const [cacheInfo, setCacheInfo] = useState<{ ageMinutes: number } | null>(null);
  const [timingAssessment, setTimingAssessment] = useState<TimingAssessment | null>(null);
  const [capabilities, setCapabilities] = useState<AssetCapabilities | null>(null);
  // Freshest price known for the current ticker, reported up by the chart's
  // live poll; panels prefer it over prices frozen in the last research run.
  const [livePrice, setLivePrice] = useState<number | null>(null);
  // Live debate state — filled progressively over the SSE custom stream.
  const [liveBull, setLiveBull] = useState<DebateCase | null>(null);
  const [liveBear, setLiveBear] = useState<DebateCase | null>(null);
  const [liveEvidence, setLiveEvidence] = useState<EvidenceItem[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    api
      .ready()
      .then(({ body }) => setReadiness(body))
      .catch(() => setReadiness(null));
    api
      .configStatus()
      .then(setConfigStatus)
      .catch(() => setConfigStatus(null));
    // Push any pre-account localStorage state (watchlist, alerts, positions,
    // levels) to the server once, then it lives with the account.
    void migrateLocalStateOnce();
  }, []);

  useEffect(() => {
    setTimingAssessment(null);
    setLivePrice(null);
    let cancelled = false;
    api
      .capabilities(ticker)
      .then((res) => {
        if (!cancelled) setCapabilities(res);
      })
      .catch(() => {
        if (!cancelled) setCapabilities(null);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  function setAgent(key: AgentKey, state: AgentState) {
    setAgents((s) => ({ ...s, [key]: state }));
  }

  function resetRun() {
    setResearch(null);
    setMeta(null);
    setCacheInfo(null);
    setLiveBull(null);
    setLiveBear(null);
    setLiveEvidence([]);
    setAgents({
      ...INITIAL_AGENT_STATES,
      sec_agent: { status: "running" },
      news_agent: { status: "running" },
      metrics_agent: { status: "running" },
      insider_agent: { status: "running" },
      signals_agent: { status: "running" },
    });
  }

  function friendlyResearchError(message: string): string {
    if (/429|too many requests|rate.?limit/i.test(message)) {
      return "Research is rate-limited right now. Wait about a minute, then try again; cached reports still load without a fresh AI run.";
    }
    if (/quota/i.test(message)) {
      return "The AI provider quota is out right now. Try again after the provider resets, or switch to a key/model with more quota.";
    }
    return `Research failed: ${message}`;
  }

  function markRunFailed(message: string) {
    setStatus(message);
    setAgents((s) => {
      const next: AgentStates = { ...s };
      (Object.keys(next) as AgentKey[]).forEach((k) => {
        if (next[k].status === "running") {
          next[k] = { status: "error", summary: "stopped" };
        }
      });
      return next;
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

  async function onResearchStream(fresh = false) {
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
          if (e.event === "ingest") {
            setStatus(e.data.detail);
            setAgent("sec_agent", {
              status: e.data.phase === "failed" ? "error" : "running",
              summary:
                e.data.phase === "started"
                  ? "downloading annual report"
                  : e.data.phase === "done"
                  ? "report indexed"
                  : "no filing available",
            });
            return;
          }
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
            // Advocate tiles get their richer summary from the debate_case
            // custom event, which arrives before this node update — keep it.
            if (node === "bull_agent" || node === "bear_agent") return;
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
            const totalUsd =
              "total_usd" in e.data.cost ? (e.data.cost.total_usd as number) : 0;
            setMeta({ duration_ms: e.data.duration_ms, cost_usd: totalUsd });
            if (e.data.cached) {
              setCacheInfo({ ageMinutes: e.data.cache_age_minutes ?? 0 });
              setAgents((s) => {
                const done: typeof s = { ...s };
                (Object.keys(done) as AgentKey[]).forEach((k) => {
                  done[k] = { status: "done", summary: "from shared cache" };
                });
                return done;
              });
              setStatus(
                `Verdict: ${e.data.result.report.recommendation} · served from a shared run`,
              );
            } else {
              setStatus(
                `Verdict: ${e.data.result.report.recommendation}` +
                  (e.data.result.report.confidence !== null
                    ? ` (${e.data.result.report.confidence}/100)`
                    : "") +
                  ` · ${(e.data.duration_ms / 1000).toFixed(1)}s · $${totalUsd.toFixed(4)}`,
              );
            }
            setHistoryRefresh((n) => n + 1);
          } else if (e.event === "error") {
            markRunFailed(friendlyResearchError(`${e.data.detail} ${e.data.error_type}`));
          }
        },
        ctl.signal,
        fresh,
        horizonDays,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        markRunFailed(friendlyResearchError((e as Error).message));
      }
    } finally {
      if (abortRef.current === ctl) abortRef.current = null;
      setBusy(false);
    }
  }

  function onCancel() {
    abortRef.current?.abort();
    markRunFailed("Cancelled");
    setBusy(false);
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
            {userRole === "owner" && (
              <button
                type="button"
                onClick={() => setShowInvites((v) => !v)}
                className={`rounded-md border px-2.5 py-1.5 ${
                  showInvites
                    ? "border-indigo-500 text-indigo-300"
                    : "border-slate-800 text-slate-300 hover:bg-slate-900"
                }`}
              >
                Invites
              </button>
            )}
            <span className="hidden text-slate-500 md:inline">{userEmail}</span>
            <button
              type="button"
              onClick={() => void onLogout()}
              className="rounded-md border border-slate-800 px-2.5 py-1.5 text-slate-300 hover:bg-slate-900"
            >
              Sign out
            </button>
            <button
              type="button"
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              aria-pressed={theme === "dark"}
              title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
              className="flex h-8 items-center gap-2 rounded-full border border-slate-800 bg-slate-900/70 px-2 text-slate-300 transition hover:border-indigo-500/60 hover:text-slate-100"
            >
              <span className="relative h-4 w-8 rounded-full border border-slate-700 bg-slate-950">
                <span
                  className={`absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full bg-indigo-300 shadow-sm shadow-indigo-900/40 transition ${
                    theme === "dark" ? "left-[17px]" : "left-1"
                  }`}
                />
              </span>
              <span className="hidden text-[11px] font-medium sm:inline">
                {theme === "dark" ? "Dark" : "Light"}
              </span>
            </button>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {tab === "scoreboard" ? (
          <>
            <ScoreboardPanel refreshKey={historyRefresh} />
            <BacktestPanel refreshKey={historyRefresh} />
          </>
        ) : (
          <>
            {showInvites && <InvitesPanel onClose={() => setShowInvites(false)} />}
            {!research && !busy && <WelcomeHero />}

            <WatchlistBar ticker={ticker} onSelect={setTicker} />

            <section className="space-y-6 rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
              <StockPicker ticker={ticker} setTicker={setTicker} />

              <StockChartPanel
                ticker={ticker}
                research={research}
                timing={timingAssessment}
                onPrice={setLivePrice}
              />

              {/* key resets the panel's result when the ticker changes, so a
                  stale assessment never shows against the new symbol. */}
              <TimingPanel key={ticker} ticker={ticker} onAssessment={setTimingAssessment} />

              <div className="grid gap-4 xl:grid-cols-2">
                <PositionTracker ticker={ticker} research={research} timing={timingAssessment} />
                <ReturnRangePanel ticker={ticker} />
              </div>

              <SmartAlertsPanel
                ticker={ticker}
                research={research}
                timing={timingAssessment}
                livePrice={livePrice}
                capabilities={capabilities}
              />

              <div className="border-t border-slate-800 pt-5">
                <div className="mb-1.5 text-xs font-medium uppercase tracking-wider text-slate-400">
                  How long would you hold it?
                </div>
                <div className="flex flex-wrap gap-2">
                  {HORIZONS.map((h) => (
                    <button
                      key={h.days}
                      onClick={() => setHorizonDays(h.days)}
                      disabled={busy}
                      title={h.hint}
                      className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition disabled:opacity-50 ${
                        horizonDays === h.days
                          ? "border-indigo-500 bg-indigo-500/15 text-indigo-200"
                          : "border-slate-700 bg-slate-950/40 text-slate-400 hover:border-slate-500 hover:text-slate-200"
                      }`}
                    >
                      {h.label}
                      {h.days === 365 && (
                        <span className="ml-1 text-[9px] text-slate-500">(52 weeks)</span>
                      )}
                    </button>
                  ))}
                </div>
                <p className="mt-1.5 text-[11px] text-slate-500">
                  The analysis is tailored to your window — a coin can be a bad 1-week bet
                  but a fine 1-year one.
                </p>

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => void onResearchStream()}
                    disabled={busy}
                    className="rounded-md bg-gradient-to-r from-indigo-600 to-cyan-600 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-900/30 transition hover:from-indigo-500 hover:to-cyan-500 disabled:opacity-50"
                  >
                    Analyze {ticker} →
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
                    One click — we fetch the reports, argue both sides, and give a verdict.
                  </span>
                </div>

                <div className="mt-4">
                  <AgentProgress states={agents} />
                </div>

                {status && <p className="mt-3 text-xs text-slate-400">{status}</p>}

                <details className="mt-4 rounded-md border border-slate-800 bg-slate-950/40">
                  <summary className="cursor-pointer select-none px-3 py-2 text-xs uppercase tracking-wider text-slate-400 hover:text-slate-200">
                    Advanced tools
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
                    <div className="flex flex-wrap items-center gap-2 border-t border-slate-800 pt-3">
                      <span className="text-[11px] text-slate-500">
                        Reports are indexed automatically on first analysis. To refresh or
                        switch report type:
                      </span>
                      <select
                        value={form}
                        onChange={(e) => setForm(e.target.value as FilingForm)}
                        className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs"
                      >
                        <option value="10-K">10-K (annual report)</option>
                        <option value="10-Q">10-Q (quarterly report)</option>
                      </select>
                      <button
                        onClick={() => void onIngest()}
                        disabled={busy}
                        className="rounded-md border border-slate-700 px-3 py-1.5 text-xs hover:bg-slate-800 disabled:opacity-50"
                      >
                        Re-index {ticker}
                      </button>
                    </div>
                  </div>
                </details>
              </div>
            </section>

            {research && (
              <div className="mt-6">
                {cacheInfo && (
                  <div className="mb-2 flex flex-wrap items-center gap-3 rounded-lg border border-cyan-500/25 bg-cyan-500/5 px-4 py-2.5 text-xs text-cyan-200">
                    <span>
                      ⚡ Served instantly from a shared run{" "}
                      {cacheInfo.ageMinutes < 1
                        ? "moments"
                        : `${Math.round(cacheInfo.ageMinutes)} min`}{" "}
                      ago — cache hits don't touch your daily quota.
                    </span>
                    <button
                      onClick={() => void onResearchStream(true)}
                      disabled={busy}
                      className="rounded-md border border-cyan-500/40 px-2.5 py-1 text-cyan-300 hover:bg-cyan-500/10 disabled:opacity-50"
                    >
                      Re-run fresh
                    </button>
                  </div>
                )}
                <VerdictCard
                  result={research}
                  meta={meta}
                  onExport={() => downloadReportMarkdown(research, meta)}
                />
              </div>
            )}

            <div className="mt-6 grid gap-4 xl:grid-cols-2">
              <CalibrationPanel report={research} refreshKey={historyRefresh} />
              <ApiStatusPanel
                config={configStatus}
                readiness={readiness}
                lastStatus={status}
                cachedAgeMinutes={cacheInfo?.ageMinutes ?? null}
              />
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <SourceQualityPanel
                research={research}
                readiness={readiness}
                config={configStatus}
                capabilities={capabilities}
              />
              <DisagreementPanel research={research} timing={timingAssessment} />
            </div>

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
