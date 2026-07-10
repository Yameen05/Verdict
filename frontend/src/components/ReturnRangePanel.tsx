import { useEffect, useRef, useState } from "react";
import { api, type ReturnRangeResponse } from "../api/client";
import { InfoTip } from "./InfoTip";

function money(value: number | null): string {
  return value === null ? "—" : `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function pct(value: number | null): string {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function ReturnRangePanel({ ticker }: { ticker: string }) {
  const [amount, setAmount] = useState("200");
  const [data, setData] = useState<ReturnRangeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Monotonic id so a slow response for an old ticker/amount can never
  // overwrite the result of a newer request.
  const requestIdRef = useRef(0);

  function load() {
    const parsed = Number(amount);
    if (!Number.isFinite(parsed) || parsed <= 0) return;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    api
      .returnRanges(ticker, parsed)
      .then((res) => {
        if (requestIdRef.current === requestId) setData(res);
      })
      .catch((e: unknown) => {
        if (requestIdRef.current === requestId) {
          setError(e instanceof Error ? e.message : "Unable to load return ranges");
        }
      })
      .finally(() => {
        if (requestIdRef.current === requestId) setLoading(false);
      });
  }

  useEffect(() => {
    setData(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker]);

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">
            Return range table
            <InfoTip label="Return range table">
              These are historical swing ranges from the last year. They are not a
              promise; they show what a normal, bad, and good window looked like.
            </InfoTip>
          </h3>
          <p className="text-[11px] text-slate-500">
            See what different holding windows could mean in dollars.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">$</span>
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") load();
            }}
            inputMode="decimal"
            className="w-24 rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-sm font-semibold text-slate-100 focus:border-cyan-500/70 focus:outline-none"
          />
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="rounded-md border border-cyan-500/50 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
          >
            {loading ? "Loading..." : "Update"}
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-rose-300">{error}</p>}

      {data && (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full min-w-[680px] text-left text-xs">
            <thead className="bg-slate-900 text-[10px] uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-3 py-2.5">Hold</th>
                <th className="px-3 py-2.5 text-right">Normal range</th>
                <th className="px-3 py-2.5 text-right">Normal move</th>
                <th className="px-3 py-2.5 text-right">Recent move</th>
                <th className="px-3 py-2.5 text-right">Bad case</th>
                <th className="px-3 py-2.5 text-right">Good case</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {data.rows.map((row) => (
                <tr key={row.horizon_days} className="bg-slate-950/40">
                  <td className="px-3 py-2 font-semibold text-slate-200">{row.label}</td>
                  <td className="px-3 py-2 text-right text-slate-200">
                    {money(row.likely_low)} - {money(row.likely_high)}
                  </td>
                  <td className="px-3 py-2 text-right text-slate-400">
                    ±{row.normal_move_pct === null ? "—" : `${row.normal_move_pct.toFixed(1)}%`}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-medium ${
                      row.recent_return_pct === null
                        ? "text-slate-500"
                        : row.recent_return_pct >= 0
                          ? "text-emerald-400"
                          : "text-rose-400"
                    }`}
                  >
                    {pct(row.recent_return_pct)}
                  </td>
                  <td className="px-3 py-2 text-right text-rose-300">
                    {money(row.worst_case)}{" "}
                    <span className="text-slate-600">({pct(row.worst_case_pct)})</span>
                  </td>
                  <td className="px-3 py-2 text-right text-emerald-300">
                    {money(row.best_case)}{" "}
                    <span className="text-slate-600">({pct(row.best_case_pct)})</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && <p className="mt-2 text-[10px] text-slate-600">{data.note}</p>}
    </section>
  );
}
