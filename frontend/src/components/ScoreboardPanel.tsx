import { useEffect, useRef, useState } from "react";
import { api, type ScoreboardEntry, type ScoreboardResponse } from "../api/client";
import { confidenceLabel, dateTime, matchesOutcomeFilter, predictionTypeLabel, money, outcomeLabel, progressPercent, returnLabel, timeRemaining, utcDate, type OutcomeFilter } from "../lib/trackRecord";
import { TrackRecordDetails } from "./TrackRecordDetails";
import { horizonLabel } from "./VerdictCard";

const OUTCOME_CHIP: Record<ScoreboardEntry["outcome"], string> = {
  hit: "bg-emerald-500/15 text-emerald-300", miss: "bg-rose-500/15 text-rose-300",
  in_progress: "bg-sky-500/15 text-sky-300", awaiting_price: "bg-amber-500/15 text-amber-300",
  unscored: "bg-slate-700/40 text-slate-400", failed: "bg-amber-500/15 text-amber-200",
};

function StatCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
    <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">{label}</div>
    <div className="mt-1 text-2xl font-bold text-slate-100">{value}</div>
    <div className="mt-1 text-xs text-slate-500">{hint}</div>
  </div>;
}

type Filter = OutcomeFilter;

export function ScoreboardPanel({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<ScoreboardResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("completed");
  const [source, setSource] = useState("all");
  const [selected, setSelected] = useState<number | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [now, setNow] = useState(Date.now());
  const clockOffset = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    async function load() {
      if (inFlight) return;
      inFlight = true;
      setLoading(true);
      try {
        const value = await api.scoreboard();
        if (!cancelled) {
          clockOffset.current = utcDate(value.server_time).getTime() - Date.now();
          setNow(Date.now() + clockOffset.current);
          setData(value);
          setError("");
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Unable to load track record");
      } finally {
        inFlight = false;
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    const interval = window.setInterval(() => { void load(); }, 60000);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, [refreshKey, refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() + clockOffset.current), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const serverNow = Date.now() + clockOffset.current;
    const deadlines = data?.entries.filter(e => e.outcome === "in_progress" && e.due_at)
      .map(e => utcDate(e.due_at!).getTime()).filter(due => due > serverNow) ?? [];
    if (!deadlines.length) return;
    // Browsers cap timeout delays at a signed 32-bit integer (~25 days).
    const delay = Math.min(Math.min(...deadlines) - serverNow + 100, 2147483647);
    const timer = window.setTimeout(() => setRefresh(v => v + 1), delay);
    return () => window.clearTimeout(timer);
  }, [data]);

  if (!data) return <p className={`mt-8 text-sm ${error ? "text-rose-400" : "text-slate-500"}`} role={error ? "alert" : undefined}>{error || "Loading verdict outcomes…"}</p>;
  const { summary, entries } = data;
  const selectedEntries = entries.filter(e => source === "all" || (e.prediction_kind ?? "ai") === source);
  const visible = selectedEntries.filter(e => matchesOutcomeFilter(e, filter));
  const finished = selectedEntries.filter(e => e.outcome === "hit" || e.outcome === "miss");
  const hits = finished.filter(e => e.outcome === "hit").length;
  const counts: Record<Filter, number> = { completed:finished.length, open:selectedEntries.filter(e => e.outcome === "in_progress" || e.outcome === "awaiting_price").length, unscored:selectedEntries.filter(e => e.outcome === "unscored").length, failed:selectedEntries.filter(e => e.outcome === "failed").length };
  const hitRate = finished.length ? hits / finished.length : null;

  return <section className="space-y-5">
    <div>
      <h2 className="text-xl font-semibold text-slate-100">Results at the end of each holding period</h2>
      <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">Issued predictions stay in progress until their original deadline, including partial analyses. Model changes keep older predictions eligible. Partial AI and rules-based predictions are labeled and can be filtered separately. {summary.rule}</p>
    </div>
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Tracked prediction hit rate" value={hitRate === null ? "—" : `${(hitRate * 100).toFixed(0)}%`} hint={finished.length ? `${hits} hits out of ${finished.length} graded predictions · ${source === "all" ? "all prediction types" : predictionTypeLabel[source as keyof typeof predictionTypeLabel]}` : "No completed outcomes in this selection"} />
      <StatCard label="Completed" value={String(counts.completed)} hint="Holding period ended and price recorded" />
      <StatCard label="In progress" value={String(counts.open)} hint={`${selectedEntries.filter(e => e.outcome === "awaiting_price").length} awaiting a completed daily price`} />
      <StatCard label="Average return on Buys" value={returnLabel((()=>{const buys=finished.filter(e=>e.recommendation === "Buy" && e.return_pct !== null);return buys.length ? buys.reduce((sum,e)=>sum+e.return_pct!,0)/buys.length : null;})())} hint="Completed Buy calls only" />
    </div>
    <label className="flex flex-wrap items-center gap-3 text-sm text-slate-300">Prediction type
      <select aria-label="Prediction type" value={source} onChange={event=>setSource(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2">
        <option value="all">All tracked types</option><option value="ai">Complete AI</option><option value="partial_ai">Partial AI</option><option value="rules_based">Rules-based</option>
      </select>
    </label>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Outcome filter">
        {([['completed', 'Completed'], ['open', 'In progress'], ['unscored', 'Unscored'], ['failed', 'Failed to assess']] as const).map(([key, label]) => <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)} className={`rounded-full border px-4 py-2 text-xs font-semibold ${filter === key ? "border-indigo-400 bg-indigo-500/15 text-indigo-200" : "border-slate-700 text-slate-400 hover:text-slate-200"}`}>{label} ({counts[key]})</button>)}
      </div>
      <button disabled={loading} onClick={() => setRefresh(v => v + 1)} className="rounded-full border border-slate-700 px-3 py-2 text-xs text-slate-400 disabled:opacity-50">{loading ? "Updating…" : "Refresh outcomes"}</button>
    </div>
    {filter === "failed" && <p className="text-sm leading-6 text-amber-200">No usable prediction was issued, or the saved result was an automatic Hold/50 failure placeholder. These attempts are excluded. Partial issued predictions remain tracked under In progress or Completed.</p>}
    {filter === "unscored" && <p className="text-sm leading-6 text-slate-400">These calls cannot be graded because required outcome data, such as the original issue price, is missing. Failed assessments have their own category.</p>}
    {error && <p role="alert" className="text-xs text-rose-300">Update failed: {error}. Showing the last loaded results.</p>}
    {visible.length === 0 ? <div className="rounded-2xl border border-dashed border-slate-800 p-8 text-sm text-slate-400">{filter === "completed" ? "No completed outcomes yet. Open In progress to see calls and their exact deadlines." : filter === "open" ? "No calls are in progress. Successfully completed analyses appear here until their selected holding periods end." : filter === "failed" ? "No failed assessments." : "No unscored calls."}</div> : <div className="overflow-x-auto rounded-2xl border border-slate-800">
      <table className="w-full min-w-[850px] text-left text-xs">
        <thead className="bg-slate-900 text-[10px] uppercase tracking-wider text-slate-500"><tr>
          {['Analysis', 'Holding period', 'Issued', 'Deadline', 'Issue price', 'Evaluation price', 'Return', 'Outcome'].map(h => <th key={h} className="px-4 py-3">{h}</th>)}
        </tr></thead>
        <tbody className="divide-y divide-slate-800/80 bg-slate-950/40">{visible.map(e => <tr key={e.id} className="hover:bg-slate-900/50">
          <td className="min-w-72 px-4 py-4"><button onClick={() => setSelected(e.id)} aria-label={`View details for ${e.ticker} run ${e.id}`} className="text-left font-semibold text-indigo-300 underline decoration-indigo-400/30 underline-offset-4 hover:text-indigo-200">{e.ticker} · {e.recommendation === "Failed" ? "Failed to assess" : e.recommendation}<span className="mt-1 block text-[10px] font-normal text-slate-500">#{e.id} · {confidenceLabel(e)} · View details</span><span className="mt-1 block text-xs text-amber-200">{predictionTypeLabel[e.prediction_kind ?? "ai"]}</span></button>{e.analysis_warning && <p className="mt-2 max-w-sm text-[11px] leading-5 text-amber-200/80">Analysis incomplete. {e.analysis_warning}</p>}{e.outcome === "failed" && <p className="mt-2 max-w-sm text-[11px] font-normal leading-5 text-amber-200/80">{e.status_reason}</p>}</td>
          <td className="px-4 py-4 text-slate-300">{e.horizon_days ? horizonLabel(e.horizon_days) : "Not recorded"}{e.horizon_assumed && <span className="block text-[10px] text-amber-300">Existing legacy assumption</span>}</td>
          <td className="px-4 py-4 text-slate-400"><time dateTime={e.created_at}>{dateTime(e.created_at)}</time></td>
          <td className="min-w-52 px-4 py-4 text-slate-300"><time dateTime={e.due_at ?? undefined}>{e.due_at ? dateTime(e.due_at) : "Not recorded"}</time>{e.outcome === "in_progress" && <><span className="mt-2 block text-[10px] text-sky-300">{timeRemaining(e.due_at!, now)}</span><div role="progressbar" aria-label={`${e.ticker} holding period`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.floor(progressPercent(e, now))} className="mt-2 h-1 overflow-hidden rounded bg-slate-800"><div className="h-full bg-sky-400" style={{ width: `${progressPercent(e, now)}%` }} /></div></>}</td>
          <td className="px-4 py-4 text-slate-300">{money(e.price_at_run)}</td>
          <td className="px-4 py-4 text-slate-300">{money(e.price_at_horizon)}</td>
          <td className="px-4 py-4 text-slate-300">{returnLabel(e.return_pct)}</td>
          <td className="px-4 py-4"><span title={e.status_reason} className={`whitespace-nowrap rounded-full px-2.5 py-1 text-[10px] font-semibold ${OUTCOME_CHIP[e.outcome]}`}>{outcomeLabel[e.outcome]}</span></td>
        </tr>)}</tbody>
      </table>
    </div>}
    <p className="text-xs text-slate-500">Showing the latest {summary.total_runs} calls. Dates use your local timezone. Outcomes update automatically every minute; grading also runs while this page is closed.</p>
    {selected !== null && <TrackRecordDetails key={selected} id={selected} onClose={() => setSelected(null)} refreshKey={now - (now % 60000)} />}
  </section>;
}
