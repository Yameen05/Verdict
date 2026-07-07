import type { ResearchResponse } from "../api/client";
import { ScoreRadar } from "./ScoreRadar";

export const VERDICT_STYLES: Record<
  string,
  { badge: string; ring: string; text: string; gauge: string }
> = {
  Buy: {
    badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
    ring: "ring-emerald-500/30",
    text: "text-emerald-300",
    gauge: "#34d399",
  },
  Hold: {
    badge: "bg-amber-500/15 text-amber-300 border-amber-500/40",
    ring: "ring-amber-500/30",
    text: "text-amber-300",
    gauge: "#fbbf24",
  },
  Sell: {
    badge: "bg-rose-500/15 text-rose-300 border-rose-500/40",
    ring: "ring-rose-500/30",
    text: "text-rose-300",
    gauge: "#fb7185",
  },
  Pending: {
    badge: "bg-slate-700/40 text-slate-300 border-slate-600",
    ring: "ring-slate-600/40",
    text: "text-slate-300",
    gauge: "#94a3b8",
  },
};

function ConfidenceGauge({ value, color }: { value: number; color: string }) {
  // Semicircle gauge: radius 44, half-circumference ≈ 138.2
  const half = Math.PI * 44;
  const filled = (Math.max(0, Math.min(100, value)) / 100) * half;
  return (
    <svg viewBox="0 0 110 62" className="w-36" role="img" aria-label={`Confidence ${value} out of 100`}>
      <path
        d="M 11 55 A 44 44 0 0 1 99 55"
        fill="none"
        stroke="#1e293b"
        strokeWidth="9"
        strokeLinecap="round"
      />
      <path
        d="M 11 55 A 44 44 0 0 1 99 55"
        fill="none"
        stroke={color}
        strokeWidth="9"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${half}`}
      />
      <text x="55" y="46" textAnchor="middle" className="fill-slate-100" fontSize="20" fontWeight="700">
        {value}
      </text>
      <text x="55" y="59" textAnchor="middle" className="fill-slate-500" fontSize="8" letterSpacing="1.5">
        CONFIDENCE
      </text>
    </svg>
  );
}

interface Props {
  result: ResearchResponse;
  meta: { duration_ms: number; cost_usd: number } | null;
  onExport: () => void;
}

export function VerdictCard({ result, meta, onExport }: Props) {
  const { report } = result;
  const style = VERDICT_STYLES[report.recommendation] ?? VERDICT_STYLES.Pending;

  return (
    <section
      className={`rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900 to-slate-950 p-6 ring-1 ${style.ring}`}
    >
      <div className="flex flex-col gap-6 lg:flex-row">
        {/* Verdict + gauge */}
        <div className="flex shrink-0 flex-col items-center gap-3 lg:w-48">
          <span className="font-mono text-sm tracking-widest text-slate-500">
            {report.ticker}
          </span>
          <span
            className={`rounded-xl border px-6 py-2 text-3xl font-bold tracking-tight ${style.badge}`}
          >
            {report.recommendation}
          </span>
          {report.confidence !== null && (
            <ConfidenceGauge value={report.confidence} color={style.gauge} />
          )}
          {meta && (
            <span className="text-[10px] text-slate-500">
              {(meta.duration_ms / 1000).toFixed(1)}s · ${meta.cost_usd.toFixed(4)}
            </span>
          )}
        </div>

        {/* The reasoning */}
        <div className="min-w-0 flex-1 space-y-4">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm leading-relaxed text-slate-100">{report.justification}</p>
            <button
              onClick={onExport}
              className="shrink-0 rounded-md border border-slate-700 px-2.5 py-1.5 text-[11px] text-slate-300 hover:bg-slate-800"
              title="Download this report as Markdown"
            >
              ↓ Export
            </button>
          </div>

          {report.dissent && (
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
              <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                Strongest opposing argument (overruled)
              </h3>
              <p className="text-xs leading-relaxed text-slate-300">{report.dissent}</p>
            </div>
          )}

          {report.falsifiers.length > 0 && (
            <div>
              <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                What would change this verdict
              </h3>
              <ul className="space-y-1">
                {report.falsifiers.map((f, i) => (
                  <li key={i} className="flex gap-2 text-xs text-slate-300">
                    <span className={style.text}>⚑</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {report.delta_summary && (
            <div className="rounded-lg border border-indigo-500/20 bg-indigo-500/5 p-3">
              <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-widest text-indigo-400">
                Since the last run
              </h3>
              <p className="text-xs leading-relaxed text-slate-300">{report.delta_summary}</p>
            </div>
          )}
        </div>

        {/* Scorecard */}
        {report.scores && (
          <div className="flex shrink-0 flex-col items-center justify-center lg:w-56">
            <ScoreRadar scores={report.scores} color={style.gauge} />
          </div>
        )}
      </div>
    </section>
  );
}
