import type { HistoryEntry } from "../api/client";

const DOT: Record<string, string> = {
  Buy: "#34d399",
  Hold: "#fbbf24",
  Sell: "#fb7185",
  Pending: "#64748b",
};

const W = 640;
const H = 150;
const PAD = { left: 46, right: 16, top: 14, bottom: 24 };

/** Price line with verdict-colored dots — verdict drift against the tape. */
export function VerdictTimeline({ runs }: { runs: HistoryEntry[] }) {
  // Oldest → newest, only runs that captured a price.
  const points = [...runs]
    .filter((r) => r.price_at_run !== null)
    .reverse();

  if (points.length < 2) return null;

  const prices = points.map((r) => r.price_at_run as number);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || max * 0.05 || 1;

  const x = (i: number) =>
    PAD.left + (i / (points.length - 1)) * (W - PAD.left - PAD.right);
  const y = (p: number) =>
    PAD.top + (1 - (p - min + span * 0.08) / (span * 1.16)) * (H - PAD.top - PAD.bottom);

  const path = points
    .map((r, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(r.price_at_run as number).toFixed(1)}`)
    .join(" ");

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <h3 className="mb-1 text-xs font-semibold text-slate-300">
        Verdict timeline{" "}
        <span className="font-normal text-slate-500">
          — price at each verdict, colored by the call
        </span>
      </h3>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Verdict history over price">
        {/* y axis ticks */}
        {[min, (min + max) / 2, max].map((p, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(p)} y2={y(p)} stroke="#1e293b" strokeWidth="1" />
            <text x={PAD.left - 6} y={y(p) + 3} textAnchor="end" fontSize="9" className="fill-slate-500">
              ${p >= 100 ? p.toFixed(0) : p.toFixed(1)}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke="#475569" strokeWidth="1.5" />
        {points.map((r, i) => (
          <g key={r.id}>
            <circle cx={x(i)} cy={y(r.price_at_run as number)} r="5" fill={DOT[r.recommendation] ?? DOT.Pending}>
              <title>
                {`${r.recommendation}${r.confidence !== null ? ` (${r.confidence})` : ""} @ $${(
                  r.price_at_run as number
                ).toFixed(2)} — ${new Date(r.created_at).toLocaleDateString()}`}
              </title>
            </circle>
            <text
              x={x(i)}
              y={H - 8}
              textAnchor="middle"
              fontSize="8"
              className="fill-slate-500"
            >
              {new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(r.created_at) ? r.created_at : r.created_at + "Z").toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </text>
          </g>
        ))}
      </svg>
      <div className="mt-1 flex gap-4 text-[10px] text-slate-500">
        {(["Buy", "Hold", "Sell"] as const).map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: DOT[k] }} />
            {k}
          </span>
        ))}
      </div>
    </div>
  );
}
