import { useEffect, useRef, useState } from "react";
import { api, type ScoreboardDetail } from "../api/client";
import { downloadReportMarkdown } from "../lib/exportMarkdown";
import { confidenceLabel, dateTime, money, outcomeLabel, predictionTypeLabel, returnLabel } from "../lib/trackRecord";
import { DebatePanel } from "./DebatePanel";
import { EvidencePanel } from "./EvidencePanel";
import { ReportPanel } from "./ReportPanel";
import { VerdictCard, horizonLabel } from "./VerdictCard";

function exportDetail(detail: ScoreboardDetail) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(detail, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `verdict-${detail.entry.ticker}-${detail.entry.id}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function TrackRecordDetails({ id, onClose, refreshKey }: {
  id: number; onClose: () => void; refreshKey: number;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [detail, setDetail] = useState<ScoreboardDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    let cancelled = false;
    setError("");
    api.scoreboardDetail(id).then((value) => {
      if (!cancelled) setDetail(value);
    }).catch((e: unknown) => {
      if (!cancelled) setError(e instanceof Error ? e.message : "Unable to load details.");
    });
    return () => { cancelled = true; };
  }, [id, refreshKey]);

  const entry = detail?.entry;
  return (
    <dialog
      ref={dialog} aria-labelledby="track-detail-title" onCancel={onClose}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      className="max-h-[92vh] w-[min(96vw,90rem)] overflow-y-auto rounded-3xl border border-slate-700 bg-slate-950 p-0 text-slate-200 shadow-2xl backdrop:bg-slate-950/80"
    >
      <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-slate-800 bg-slate-950 px-6 py-4">
        <div>
          <p className="text-xs text-slate-400">Original analysis · Run #{id}</p>
          <h2 id="track-detail-title" className="font-display text-xl">
            {entry ? `${entry.ticker} · ${entry.recommendation === "Failed" ? "Failed to assess" : entry.recommendation} · ${entry.horizon_days ? horizonLabel(entry.horizon_days) : "Horizon not recorded"}` : "Verdict details"}
          </h2>
        </div>
        <div className="flex gap-2">
          {detail && <button onClick={() => exportDetail(detail)} className="rounded-full border border-slate-700 px-3 py-2 text-xs">Download all details</button>}
          <button autoFocus onClick={onClose} className="rounded-full border border-slate-700 px-3 py-2 text-xs">Close details</button>
        </div>
      </header>
      <div className="space-y-6 p-5 sm:p-7">
        {error && <p role="alert" className="text-rose-300">{error}</p>}
        {!detail && !error && <p className="text-slate-400">Loading the saved analysis…</p>}
        {detail && entry && <>
          <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-lg font-semibold">{outcomeLabel[entry.outcome]}</h3>
              <span className="text-xs text-slate-400">{confidenceLabel(entry)}</span>
            </div>
            <p className="mt-2 text-sm text-slate-300">{entry.status_reason}</p>
            <p className="mt-2 text-sm text-amber-200">{predictionTypeLabel[entry.prediction_kind ?? "ai"]}{entry.analysis_warning ? ` · Analysis incomplete. ${entry.analysis_warning}` : ""}</p>
            <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
              {[
                ["Issued", dateTime(entry.created_at)],
                ["Holding period ends", entry.due_at ? dateTime(entry.due_at) : "Not recorded"],
                ["Holding period", entry.horizon_days ? `${entry.horizon_days} calendar days` : "Not recorded"],
                ["Issue price", money(entry.price_at_run)],
                ["Evaluation price", money(entry.price_at_horizon)],
                ["Return over the holding period", returnLabel(entry.return_pct)],
                ["Daily candle starts", entry.price_bar_at ? dateTime(entry.price_bar_at) : "Not available yet"],
                ["Daily candle completes", entry.evaluated_at ? dateTime(entry.evaluated_at) : "Not available yet"],
                ["Model at issue", entry.model ?? "Not recorded"],
                ["Analysis duration", detail.duration_ms === null ? "Not recorded" : `${(detail.duration_ms / 1000).toFixed(1)} seconds`],
                ["Analysis cost", detail.cost_usd === null ? "Not recorded" : `$${detail.cost_usd.toFixed(4)}`],
                ["Run ID", String(entry.id)],
              ].map(([label, value]) => <div key={label}><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 break-words">{value}</dd></div>)}
            </dl>
            {entry.horizon_assumed && <p className="mt-4 text-xs text-amber-300">This older run’s saved evaluation already used an assumed holding period. That existing evaluation is preserved; no new deadline was invented.</p>}
            <p className="mt-4 border-t border-slate-800 pt-4 text-xs leading-6 text-slate-400">{detail.rule} Daily candle completion is a conservative cutoff, not an exchange closing timestamp. Finished grades are saved and do not change with later prices.</p>
          </section>
          {detail.result ? <>
            <h3 className="font-display text-xl">The original verdict</h3>
            <VerdictCard result={detail.result} meta={detail.duration_ms !== null && detail.cost_usd !== null ? { duration_ms: detail.duration_ms, cost_usd: detail.cost_usd } : null} onExport={() => { if (detail.result) downloadReportMarkdown(detail.result, null); }} />
            <ReportPanel result={detail.result} />
            <DebatePanel bull={detail.result.bull} bear={detail.result.bear} evidence={detail.result.evidence} live={false} />
            <EvidencePanel evidence={detail.result.evidence} />
          </> : <section><h3 className="font-display text-xl">Original reasoning</h3><p className="mt-2 text-sm leading-7 text-slate-300">{detail.justification}</p><p className="mt-2 text-xs text-slate-500">This older run has an incomplete report. All saved fields are available below.</p></section>}
          <details className="rounded-xl border border-slate-800 p-4">
            <summary className="cursor-pointer text-sm font-semibold">All saved analysis data</summary>
            <pre className="mt-4 max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-400">{JSON.stringify(detail.payload, null, 2)}</pre>
          </details>
        </>}
      </div>
    </dialog>
  );
}
