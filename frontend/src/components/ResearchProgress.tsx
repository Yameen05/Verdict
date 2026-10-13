import { type ProgressState, progressPercent } from "../lib/researchProgress";

export function ResearchProgress({ state }: { state: ProgressState }) {
  if (state.phase === "cached") return <p role="status" className="text-sm text-slate-300">Loaded a saved report · no fresh research run</p>;
  const percent = progressPercent(state);
  const waits = Object.values(state.waits);
  const waiting = waits.includes("capacity")
    ? "Google is busy. A check is waiting before one retry."
    : waits.length ? "A check is queued for the next AI request slot. Other checks may continue." : null;
  return (
    <section aria-label="Research progress" className="space-y-2 rounded-xl border border-slate-700 bg-slate-900/70 p-4">
      <div className="flex items-start justify-between gap-3 text-sm">
        <p role="status" aria-live="polite" className="min-w-0 text-slate-200">{state.label}</p>
        <span className="shrink-0 font-semibold tabular-nums text-indigo-300">{percent}%</span>
      </div>
      <div role="progressbar" aria-label="Research steps completed" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-valuetext={`${percent}% of research steps completed. ${state.label}`} className="h-2.5 overflow-hidden rounded-full bg-slate-800">
        <div className={`h-full rounded-full ${state.phase === "error" || state.phase === "partial" ? "bg-amber-400" : "bg-indigo-400"}`} style={{ width: `${percent}%` }} />
      </div>
      {(state.phase === "error" || state.phase === "partial") && <p className="text-sm font-medium text-amber-200">Confidence: {state.phase === "partial" && !state.label.startsWith("Failed to assess") ? "Not assessed — analysis incomplete" : "Failed to assess"}</p>}
      {waiting && <p role="status" aria-live="polite" className="text-xs text-amber-200">{waiting}</p>}
      <p className="text-xs text-slate-400">Completed steps, not time remaining. Some checks run together.</p>
    </section>
  );
}
