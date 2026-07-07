import { useEffect, useState } from "react";
import { api, type HistoryEntry } from "../api/client";
import { VerdictTimeline } from "./VerdictTimeline";

interface Props {
  ticker: string;
  refreshKey: number; // bump to force a refetch (after a new research run)
}

const RECOMMENDATION_COLORS: Record<string, string> = {
  Buy: "text-emerald-400",
  Hold: "text-amber-400",
  Sell: "text-rose-400",
  Pending: "text-slate-400",
};

function relativeTime(iso: string): string {
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso);
  const normalized = hasTimezone ? iso : `${iso}Z`;
  const then = new Date(normalized).getTime();
  if (Number.isNaN(then)) return "";

  const diff = Math.max(0, Date.now() - then);
  const s = Math.floor(diff / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function HistoryPanel({ ticker, refreshKey }: Props) {
  const [runs, setRuns] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    api
      .history(ticker, 10)
      .then((r) => {
        setRuns(r.runs);
      })
      .catch((e: unknown) => {
        setRuns([]);
        setError(e instanceof Error ? e.message : "Unable to load history");
      })
      .finally(() => setLoading(false));
  }, [ticker, refreshKey]);

  if (loading && runs.length === 0) {
    return <p className="text-xs text-slate-500">Loading history…</p>;
  }
  if (error) {
    return <p className="text-xs text-rose-400">History unavailable: {error}</p>;
  }
  if (runs.length === 0) {
    return (
      <p className="text-xs text-slate-500">
        No prior reports for {ticker}. Run one to build history.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <VerdictTimeline runs={runs} />
      <ul className="divide-y divide-slate-800 rounded-lg border border-slate-800">
        {runs.map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-3 px-3 py-2 text-xs">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span
                  className={`font-semibold ${
                    RECOMMENDATION_COLORS[r.recommendation] ?? "text-slate-400"
                  }`}
                >
                  {r.recommendation}
                </span>
                {r.confidence !== null && (
                  <span className="rounded bg-slate-800 px-1 py-px text-[9px] text-slate-400">
                    {r.confidence}/100
                  </span>
                )}
                {r.price_at_run !== null && (
                  <span className="text-slate-500">@ ${r.price_at_run.toFixed(2)}</span>
                )}
                <span className="text-slate-500">·</span>
                <span className="text-slate-500">{relativeTime(r.created_at)}</span>
              </div>
              <div className="truncate text-[11px] text-slate-500">{r.justification}</div>
            </div>
            <div className="shrink-0 text-right text-[10px] text-slate-500">
              {r.cost_usd !== null && <div>${r.cost_usd.toFixed(4)}</div>}
              {r.duration_ms !== null && <div>{(r.duration_ms / 1000).toFixed(1)}s</div>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
