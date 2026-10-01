import { useEffect, useRef, useState } from "react";
import { StockPicker, POPULAR_STOCKS } from "./components/StockPicker";
import { QueryResultPanel } from "./components/QueryResult";
import { ReportPanel } from "./components/ReportPanel";
import { AgentProgress, type AgentKey, type AgentState } from "./components/AgentProgress";
import { HistoryPanel } from "./components/HistoryPanel";
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
import { DayTradePage } from "./components/daytrade/DayTradePage";
import { LegalModal } from "./components/LegalModal";
import { AppShell, type AppSection } from "./components/AppShell";
import { downloadReportMarkdown } from "./lib/exportMarkdown";
import { FOOTER_DISCLAIMER } from "./lib/legal";
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
type Tab = AppSection;
type ResearchView = "verdict" | "market" | "position" | "details";

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

function HistoryTickerInput({ onApply }: { onApply: (t: string) => void }) {
  const [value, setValue] = useState("");
  function apply() {
    const t = value.trim().toUpperCase();
    if (t) {
      onApply(t);
      setValue("");
    }
  }
  return (
    <div className="flex gap-2">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value.toUpperCase())}
        onKeyDown={(e) => e.key === "Enter" && apply()}
        placeholder="Any ticker…"
        className="w-36 rounded-full border border-slate-700 bg-slate-950 px-3.5 py-1.5 font-mono text-xs uppercase placeholder-slate-600 focus:border-indigo-500 focus:outline-none"
      />
      <button
        type="button"
        onClick={apply}
        disabled={!value.trim()}
        className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-slate-100 disabled:opacity-50"
      >
        Load
      </button>
    </div>
  );
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

const RESEARCH_VIEWS: { id: ResearchView; label: string }[] = [
  { id: "verdict", label: "Verdict" },
  { id: "market", label: "Price & timing" },
  { id: "position", label: "My position" },
  { id: "details", label: "Sources & details" },
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
  const [tab, setTab] = useState<Tab>("research");
  const [researchView, setResearchView] = useState<ResearchView>("verdict");
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
            setResearchView("verdict");
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
                  ` · ${(e.data.duration_ms / 1000).toFixed(1)}s · $${totalUsd.toFixed(4)}` +
                  (e.data.persist_error
                    ? " · not saved to history (try again to retry saving)"
                    : ""),
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

  const readinessSummary: { state: "checking" | "ready" | "degraded"; text: string } =
    readiness === null
      ? { state: "checking", text: "Checking the research services…" }
      : readiness.status === "ready"
      ? { state: "ready", text: "All research services are ready." }
      : {
          state: "degraded",
          text:
            "Some services are limited: " +
            (Object.entries(readiness.checks ?? {})
              .filter(([, c]) => !c.ok)
              .map(([k]) => k)
              .join(", ") || "unknown"),
        };

  const showDebate = busy || research !== null;
  const debateBull = research?.bull ?? liveBull;
  const debateBear = research?.bear ?? liveBear;
  const debateEvidence = research?.evidence ?? liveEvidence;

  return (
    <AppShell
      activeSection={tab}
      onSectionChange={setTab}
      userEmail={userEmail}
      userRole={userRole}
      onLogout={onLogout}
      theme={theme}
      onThemeChange={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
      readiness={readinessSummary}
      invitesOpen={showInvites}
      onInvitesClick={() => {
        setTab("research");
        setShowInvites((value) => !value);
      }}
    >
      <main className="mx-auto max-w-[90rem] px-4 py-7 sm:px-6 sm:py-9 xl:px-10">
        {tab === "scoreboard" && (
          <div className="space-y-6">
            <header className="max-w-3xl">
              <p className="text-sm font-semibold text-indigo-300">Track record</p>
              <h1 className="mt-1 font-display text-3xl font-medium tracking-tight text-slate-50 sm:text-4xl">
                See how past verdicts performed
              </h1>
              <p className="mt-2 text-base leading-7 text-slate-400">
                Every call is measured against what happened next, so you can judge whether
                Verdict's confidence is earned.
              </p>
            </header>
            <ScoreboardPanel refreshKey={historyRefresh} />
            <BacktestPanel refreshKey={historyRefresh} />
          </div>
        )}

        {tab === "daytrade" && <DayTradePage />}

        {tab === "analyst" && (
          <div className="mx-auto max-w-4xl">
            <section>
              <p className="text-sm font-semibold text-indigo-300">Ask analyst</p>
              <h1 className="mt-1 font-display text-3xl font-medium tracking-tight text-slate-50 sm:text-4xl">
                Ask about your latest research
              </h1>
              <p className="mt-2 max-w-2xl text-base leading-7 text-slate-400">
                Get a plain-English answer grounded in your latest research run
                {research ? (
                  <>
                    {" "}
                    for <span className="font-mono text-indigo-300">{research.report.ticker}</span>
                  </>
                ) : (
                  " — run an analysis from Research first"
                )}
                . Money questions use the figures in the report rather than invented estimates.
              </p>
            </section>
            <ChatPanel ticker={ticker} research={research} />
          </div>
        )}

        {tab === "history" && (
          <div className="mx-auto max-w-5xl space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-indigo-300">History</p>
                <h1 className="mt-1 font-display text-3xl font-medium tracking-tight text-slate-50 sm:text-4xl">
                  Review earlier verdicts
                </h1>
                <p className="mt-2 max-w-2xl text-base leading-7 text-slate-400">
                  Every past verdict for{" "}
                  <span className="font-mono text-indigo-300">{ticker}</span>{" "}
                  <span className="text-slate-500">({companyName(ticker)})</span>, plotted against
                  the price at the time of each call.
                </p>
              </div>
              <HistoryTickerInput onApply={setTicker} />
            </div>
            <WatchlistBar ticker={ticker} onSelect={setTicker} />
            <HistoryPanel ticker={ticker} refreshKey={historyRefresh} />
          </div>
        )}

        {tab === "research" && (
          <div className="space-y-5">
            {showInvites && <InvitesPanel onClose={() => setShowInvites(false)} />}
            <header className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-indigo-300">Research</p>
                <h1 className="mt-1 font-display text-3xl font-medium tracking-tight text-slate-50 sm:text-4xl">
                  {ticker} <span className="text-slate-500">· {companyName(ticker)}</span>
                </h1>
              </div>
            </header>

            <section className="rounded-2xl border border-slate-700/80 bg-slate-900/60 p-4 shadow-lg shadow-slate-950/20 sm:p-5">
              <div className="grid items-end gap-4 lg:grid-cols-[minmax(18rem,1fr)_15rem_12rem]">
                <StockPicker ticker={ticker} setTicker={setTicker} />

                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-slate-200">
                    Holding period
                  </span>
                  <select
                    value={horizonDays}
                    onChange={(event) => setHorizonDays(Number(event.target.value))}
                    disabled={busy}
                    className="min-h-12 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 text-base text-slate-100 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-50"
                  >
                    {HORIZONS.map((horizon) => (
                      <option key={horizon.days} value={horizon.days}>
                        {horizon.label}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void onResearchStream()}
                    disabled={busy}
                    className="min-h-12 flex-1 rounded-xl bg-indigo-600 px-5 text-base font-semibold text-white shadow-lg shadow-indigo-950/40 transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {busy ? "Analyzing…" : "Analyze"}
                  </button>
                  {busy && (
                    <button
                      type="button"
                      onClick={onCancel}
                      className="min-h-12 rounded-xl border border-rose-700 px-4 text-sm font-medium text-rose-300 transition hover:bg-rose-900/30"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>

              {(busy || status) && (
                <div aria-live="polite" className="mt-4 border-t border-slate-800 pt-4">
                  {busy && <AgentProgress states={agents} />}
                  {status && <p className={`${busy ? "mt-3" : ""} text-sm leading-6 text-slate-400`}>{status}</p>}
                </div>
              )}
            </section>

            <WatchlistBar ticker={ticker} onSelect={setTicker} />

            <nav
              aria-label="Research sections"
              className="research-tabs"
              role="tablist"
            >
              {RESEARCH_VIEWS.map((view) => (
                <button
                  key={view.id}
                  type="button"
                  role="tab"
                  aria-selected={researchView === view.id}
                  onClick={() => setResearchView(view.id)}
                  className={researchView === view.id ? "is-active" : ""}
                >
                  {view.label}
                </button>
              ))}
            </nav>

            {researchView === "verdict" && (
              <section aria-labelledby="latest-verdict-title">
                {research ? (
                  <>
                    <div className="mb-3 flex items-end justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-indigo-300">Latest result</p>
                        <h2 id="latest-verdict-title" className="font-display text-2xl text-slate-50">
                          The verdict on {research.report.ticker}
                        </h2>
                      </div>
                    </div>
                    {cacheInfo && (
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-cyan-500/25 bg-cyan-500/5 px-4 py-3 text-sm text-cyan-200">
                        <span>
                          Shared result from{" "}
                          {cacheInfo.ageMinutes < 1
                            ? "moments ago"
                            : `${Math.round(cacheInfo.ageMinutes)} minutes ago`}.
                        </span>
                        <button
                          type="button"
                          onClick={() => void onResearchStream(true)}
                          disabled={busy}
                          className="min-h-10 rounded-lg border border-cyan-500/40 px-3 text-sm font-medium text-cyan-300 hover:bg-cyan-500/10 disabled:opacity-50"
                        >
                          Run fresh
                        </button>
                      </div>
                    )}
                    <VerdictCard
                      result={research}
                      meta={meta}
                      onExport={() => downloadReportMarkdown(research, meta)}
                    />
                  </>
                ) : (
                  <div className="grid min-h-64 place-items-center rounded-2xl border border-dashed border-slate-700 bg-slate-900/20 px-6 text-center">
                    <div>
                      <p className="font-display text-2xl text-slate-200">No verdict yet</p>
                      <p className="mt-1 text-sm text-slate-500">{ticker} has not been analyzed in this session.</p>
                    </div>
                  </div>
                )}
              </section>
            )}

            {researchView === "market" && (
              <section className="space-y-5" aria-labelledby="market-chart-title">
                <header className="max-w-3xl">
                  <h2 id="market-chart-title" className="font-display text-3xl text-slate-50">
                    Price & entry timing
                  </h2>
                  <p className="mt-1 text-base leading-7 text-slate-400">
                    The chart shows what the price has done. Entry timing checks whether today's setup looks favorable.
                  </p>
                </header>
                <StockChartPanel
                  ticker={ticker}
                  research={research}
                  timing={timingAssessment}
                  onPrice={setLivePrice}
                />
                <TimingPanel key={ticker} ticker={ticker} onAssessment={setTimingAssessment} />
              </section>
            )}

            {researchView === "position" && (
              <section className="space-y-5" aria-labelledby="position-title">
                <header className="max-w-3xl">
                  <h2 id="position-title" className="font-display text-3xl text-slate-50">
                    My {ticker} position
                  </h2>
                  <p className="mt-1 text-base leading-7 text-slate-400">
                    Track something you already own, or test what a new dollar amount could look like.
                  </p>
                </header>
                <PositionTracker ticker={ticker} research={research} timing={timingAssessment} />
                <ReturnRangePanel ticker={ticker} />
                <SmartAlertsPanel
                  ticker={ticker}
                  research={research}
                  timing={timingAssessment}
                  livePrice={livePrice}
                  capabilities={capabilities}
                />
              </section>
            )}

            {researchView === "details" && (
              <section className="space-y-5" aria-labelledby="details-title">
                <header className="max-w-3xl">
                  <h2 id="details-title" className="font-display text-3xl text-slate-50">
                    Sources & details
                  </h2>
                  <p className="mt-1 text-base leading-7 text-slate-400">
                    Filing search, evidence, debate, and data-provider status.
                  </p>
                </header>

                <section className="rounded-2xl border-l-4 border-l-cyan-600 border-y border-r border-slate-800 bg-slate-900/45 p-5">
                  <h3 className="text-base font-semibold text-slate-100">Search the company filing</h3>
                  <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(16rem,1fr)_13rem_auto]">
                    <textarea
                      id="filing-question"
                      aria-label={`Question about ${ticker}'s filing`}
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      rows={2}
                      className="min-h-12 w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-3 text-base placeholder-slate-600 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
                    />
                    <select
                      aria-label="Filing type"
                      value={form}
                      onChange={(e) => setForm(e.target.value as FilingForm)}
                      className="min-h-12 rounded-xl border border-slate-700 bg-slate-950 px-3 text-sm"
                    >
                      <option value="10-K">Annual report (10-K)</option>
                      <option value="10-Q">Quarterly report (10-Q)</option>
                    </select>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={onQuery}
                        disabled={busy}
                        className="min-h-12 rounded-xl bg-cyan-700 px-4 text-sm font-semibold text-white hover:bg-cyan-600 disabled:opacity-50"
                      >
                        Search
                      </button>
                      <button
                        type="button"
                        onClick={() => void onIngest()}
                        disabled={busy}
                        className="min-h-12 rounded-xl border border-slate-700 px-4 text-sm font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                      >
                        Refresh data
                      </button>
                    </div>
                  </div>
                </section>

                <QueryResultPanel result={queryResult} />

                {showDebate ? (
                  <div className="space-y-4">
                    <DebatePanel
                      bull={debateBull}
                      bear={debateBear}
                      evidence={debateEvidence}
                      live={busy && !research}
                    />
                    <ReportPanel result={research} />
                    <EvidencePanel evidence={research?.evidence ?? []} />
                    {research && (
                      <>
                        <SourceQualityPanel
                          research={research}
                          readiness={readiness}
                          config={configStatus}
                          capabilities={capabilities}
                        />
                        <div className="grid gap-4 xl:grid-cols-2">
                          <CalibrationPanel report={research} refreshKey={historyRefresh} />
                          <DisagreementPanel research={research} timing={timingAssessment} />
                        </div>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-slate-700 px-5 py-8 text-center text-sm text-slate-500">
                    Evidence and debate will appear here after an analysis.
                  </div>
                )}

                <details className="workspace-section">
                  <summary>
                    <span>
                      <strong>System details</strong>
                      <small>Data-provider availability, cache details, and diagnostics</small>
                    </span>
                  </summary>
                  <div className="border-t border-slate-800 p-4 sm:p-6">
                    <ApiStatusPanel
                      config={configStatus}
                      readiness={readiness}
                      lastStatus={status}
                      cachedAgeMinutes={cacheInfo?.ageMinutes ?? null}
                    />
                  </div>
                </details>
              </section>
            )}
          </div>
        )}

        <AppFooter />
      </main>
    </AppShell>
  );
}

function AppFooter() {
  const [legalDoc, setLegalDoc] = useState<"risk" | "terms" | "privacy" | null>(null);
  return (
    <footer className="mt-14 border-t border-slate-800/60 pb-4 pt-7 text-center text-xs text-slate-500">
      <p className="mx-auto max-w-2xl leading-relaxed">{FOOTER_DISCLAIMER}</p>
      <p className="mt-2 flex items-center justify-center gap-3">
        <button
          type="button"
          onClick={() => setLegalDoc("risk")}
          className="underline decoration-slate-700 underline-offset-2 hover:text-slate-300"
        >
          Risk & data disclosure
        </button>
        <span aria-hidden="true">·</span>
        <button
          type="button"
          onClick={() => setLegalDoc("terms")}
          className="underline decoration-slate-700 underline-offset-2 hover:text-slate-300"
        >
          Terms of use
        </button>
        <span aria-hidden="true">·</span>
        <button
          type="button"
          onClick={() => setLegalDoc("privacy")}
          className="underline decoration-slate-700 underline-offset-2 hover:text-slate-300"
        >
          Privacy policy
        </button>
      </p>
      {legalDoc && <LegalModal initialDoc={legalDoc} onClose={() => setLegalDoc(null)} />}
    </footer>
  );
}
