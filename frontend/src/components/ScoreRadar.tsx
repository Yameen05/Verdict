import type { DimensionScores } from "../api/client";

const AXES: { key: keyof DimensionScores; label: string }[] = [
  { key: "valuation", label: "Valuation" },
  { key: "growth", label: "Growth" },
  { key: "profitability", label: "Profit" },
  { key: "balance_sheet", label: "Balance" },
  { key: "sentiment", label: "Sentiment" },
];

const CX = 110;
const CY = 100;
const R = 62;

function point(axis: number, radius: number): [number, number] {
  const angle = (Math.PI * 2 * axis) / AXES.length - Math.PI / 2;
  return [CX + radius * Math.cos(angle), CY + radius * Math.sin(angle)];
}

export function ScoreRadar({ scores, color }: { scores: DimensionScores; color: string }) {
  const values = AXES.map(({ key }) => {
    const v = scores[key];
    return v === null || v === undefined ? 0 : Math.max(0, Math.min(10, v));
  });
  const polygon = values
    .map((v, i) => point(i, (v / 10) * R).join(","))
    .join(" ");

  return (
    <svg viewBox="0 0 220 200" className="w-full max-w-[220px]" role="img" aria-label="Dimension scorecard">
      {/* grid rings */}
      {[0.33, 0.66, 1].map((f) => (
        <polygon
          key={f}
          points={AXES.map((_, i) => point(i, R * f).join(",")).join(" ")}
          fill="none"
          stroke="#1e293b"
          strokeWidth="1"
        />
      ))}
      {/* spokes */}
      {AXES.map((_, i) => {
        const [x, y] = point(i, R);
        return <line key={i} x1={CX} y1={CY} x2={x} y2={y} stroke="#1e293b" strokeWidth="1" />;
      })}
      {/* the shape */}
      <polygon points={polygon} fill={color} fillOpacity="0.18" stroke={color} strokeWidth="1.5" />
      {values.map((v, i) => {
        const [x, y] = point(i, (v / 10) * R);
        return <circle key={i} cx={x} cy={y} r="2.5" fill={color} />;
      })}
      {/* labels + values */}
      {AXES.map(({ label, key }, i) => {
        const [x, y] = point(i, R + 20);
        const raw = scores[key];
        return (
          <text
            key={label}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="9"
            className="fill-slate-400"
          >
            {label}
            <tspan x={x} dy="10" fontSize="8" className="fill-slate-500">
              {raw === null || raw === undefined ? "–" : raw.toFixed(0) + "/10"}
            </tspan>
          </text>
        );
      })}
    </svg>
  );
}
