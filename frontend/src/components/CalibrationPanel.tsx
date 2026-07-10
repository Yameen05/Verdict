import { useEffect, useMemo, useState } from "react";
import { api, type BacktestResponse, type ResearchResponse } from "../api/client";
import { InfoTip } from "./InfoTip";
import { horizonLabel } from "./VerdictCard";

export function CalibrationPanel({
  report,
  refreshKey,
}: {
  report: ResearchResponse | null;
  refreshKey: number;
}) {
  const [data, setData] = useState<BacktestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .backtest()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Calibration unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const horizon = report?.report.horizon_days ?? 14;
  const match = useMemo(() => {
    if (!data) return null;
    return data.summary.by_horizon.find((h) => h.horizon_days === horizon) ?? null;
  }, [data, horizon]);

  if (!report && !data) return null;

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
      <h3 className="text-sm font-semibold text-slate-100">
        Confidence calibration
        <InfoTip label="Confidence calibration">
          This checks matured past verdicts at the same holding window. Small samples
          are useful context, not proof the next call will be right.
        </InfoTip>
      </h3>
      {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
      {data && (
        <div className="mt-3 grid gap-3 sm:grid-cols-4">
          <Card
            label={`${horizonLabel(horizon)} track record`}
            value={
              match?.hit_rate == null ? "Not enough yet" : `${(match.hit_rate * 100).toFixed(0)}%`
            }
            hint={match ? `${match.hits} hits / ${match.scored} scored` : "no matured verdicts"}
          />
          <Card
            label="All matured verdicts"
            value={
              data.summary.hit_rate == null
                ? "—"
                : `${(data.summary.hit_rate * 100).toFixed(0)}%`
            }
            hint={`${data.summary.hits} hits / ${data.summary.scored} scored`}
          />
          <Card
            label="Avg horizon return"
            value={
              match?.avg_return_pct == null
                ? "—"
                : `${match.avg_return_pct > 0 ? "+" : ""}${match.avg_return_pct.toFixed(1)}%`
            }
            hint="matured calls only"
          />
          <Card
            label="Brier score"
            value={data.summary.brier_score == null ? "—" : data.summary.brier_score.toFixed(3)}
            hint="0 = perfectly calibrated; 0.25 = coin flip"
          />
        </div>
      )}

      {data && data.summary.by_confidence.length > 0 && (
        <div className="mt-3">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Hit rate by stated confidence
            <InfoTip label="Hit rate by stated confidence">
              If the app is well calibrated, higher-confidence calls should hit
              more often. Big gaps mean the confidence number should be trusted
              less.
            </InfoTip>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {data.summary.by_confidence.map((bucket) => (
              <span
                key={bucket.label}
                className="rounded-md border border-slate-800 bg-slate-900/60 px-2 py-1 text-[11px] text-slate-300"
              >
                <span className="font-semibold text-slate-100">{bucket.label}</span>
                {": "}
                {bucket.hit_rate == null ? "—" : `${(bucket.hit_rate * 100).toFixed(0)}%`}
                <span className="text-slate-500"> ({bucket.hits}/{bucket.scored})</span>
              </span>
            ))}
          </div>
        </div>
      )}
      {report && (
        <p className="mt-3 text-xs leading-relaxed text-slate-400">
          Current call:{" "}
          <span className="font-semibold text-slate-100">
            {report.report.recommendation}
          </span>{" "}
          for a {horizonLabel(horizon)} hold
          {report.report.confidence !== null ? ` at ${report.report.confidence}/100 confidence.` : "."}
        </p>
      )}
    </section>
  );
}

function Card({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-xl font-bold text-slate-100">{value}</div>
      <div className="mt-0.5 text-[10px] text-slate-500">{hint}</div>
    </div>
  );
}
