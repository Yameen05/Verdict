import { useEffect, useState } from "react";
import { api, type ScoreboardResponse } from "../api/client";

const REC_COLOR: Record<string, string> = {
  Buy: "text-emerald-400",
  Hold: "text-amber-400",
  Sell: "text-rose-400",
  Pending: "text-slate-400",
};

const OUTCOME_CHIP: Record<string, string> = {
  hit: "bg-emerald-500/15 text-emerald-300",
  miss: "bg-rose-500/15 text-rose-300",
  unscored: "bg-slate-700/40 text-slate-500",
};

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold text-slate-100">{value}</div>
      {hint && <div className="mt-0.5 text-[10px] text-slate-500">{hint}</div>}
    </div>
  );
}

export function ScoreboardPanel({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<ScoreboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .scoreboard()
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Unable to load scoreboard"),
      )
      .finally(() => setLoading(false));
  }, [refreshKey]);

  if (loading && !data) {
    return <p className="mt-8 text-sm text-slate-500">Grading past verdicts…</p>;
  }
  if (error) {
    return <p className="mt-8 text-sm text-rose-400">Scoreboard unavailable: {error}</p>;
  }
  if (!data) return null;

  const { summary, entries } = data;

  return (
    <section className="mt-6">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-slate-100">The scoreboard</h2>
        <p className="mt-0.5 text-xs text-slate-400">
          Verdict grades its own homework: every stored verdict is measured against the
          price move since it was issued. {summary.rule}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Hit rate"
          value={summary.hit_rate === null ? "—" : `${(summary.hit_rate * 100).toFixed(0)}%`}
          hint={summary.scored ? `${summary.hits} of ${summary.scored} scored verdicts` : "no scored verdicts yet"}
        />
        <StatCard label="Verdicts issued" value={String(summary.total_runs)} />
        <StatCard label="Scored" value={String(summary.scored)} hint="had a captured price + a non-Pending call" />
        <StatCard
          label="Avg return on Buys"
          value={
            summary.avg_return_buy_pct === null
              ? "—"
              : `${summary.avg_return_buy_pct > 0 ? "+" : ""}${summary.avg_return_buy_pct.toFixed(1)}%`
          }
          hint="since each Buy verdict"
        />
      </div>

      {entries.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">
          No research runs yet — run one from the Research tab and come back.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead className="bg-slate-900 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2.5">Ticker</th>
                <th className="px-3 py-2.5">Verdict</th>
                <th className="px-3 py-2.5">Conf.</th>
                <th className="px-3 py-2.5">Issued</th>
                <th className="px-3 py-2.5 text-right">Price then</th>
                <th className="px-3 py-2.5 text-right">Now</th>
                <th className="px-3 py-2.5 text-right">Return</th>
                <th className="px-3 py-2.5">Outcome</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 bg-slate-950/40">
              {entries.map((e) => (
                <tr key={e.id} className="hover:bg-slate-900/50">
                  <td className="px-3 py-2 font-mono font-semibold text-indigo-300">{e.ticker}</td>
                  <td className={`px-3 py-2 font-semibold ${REC_COLOR[e.recommendation] ?? ""}`}>
                    {e.recommendation}
                  </td>
                  <td className="px-3 py-2 text-slate-400">{e.confidence ?? "—"}</td>
                  <td className="px-3 py-2 text-slate-400">
                    {new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(e.created_at) ? e.created_at : e.created_at + "Z").toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-300">
                    {e.price_at_run === null ? "—" : `$${e.price_at_run.toFixed(2)}`}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-300">
                    {e.current_price === null ? "—" : `$${e.current_price.toFixed(2)}`}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-medium ${
                      e.return_pct === null
                        ? "text-slate-500"
                        : e.return_pct >= 0
                        ? "text-emerald-400"
                        : "text-rose-400"
                    }`}
                  >
                    {e.return_pct === null
                      ? "—"
                      : `${e.return_pct > 0 ? "+" : ""}${e.return_pct.toFixed(1)}%`}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase ${OUTCOME_CHIP[e.outcome]}`}
                    >
                      {e.outcome}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
