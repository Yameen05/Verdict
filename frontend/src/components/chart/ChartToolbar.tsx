import { ToolbarButton } from "./ChartControls";

export type ChartStyle = "candles" | "area" | "line";

export type ToggleKey =
  | "volume"
  | "ma20"
  | "ma50"
  | "boll"
  | "rsi"
  | "macd"
  | "log"
  | "live"
  | "verdicts"
  | "events"
  | "decisionLines";

const TOGGLES: { key: ToggleKey; label: string }[] = [
  { key: "volume", label: "Volume" },
  { key: "ma20", label: "SMA 20" },
  { key: "ma50", label: "SMA 50" },
  { key: "boll", label: "Boll" },
  { key: "rsi", label: "RSI" },
  { key: "macd", label: "MACD" },
  { key: "log", label: "Log" },
  { key: "live", label: "Live" },
  { key: "verdicts", label: "Verdicts" },
  { key: "events", label: "Events" },
  { key: "decisionLines", label: "Decision lines" },
];

export function ChartToolbar({
  chartStyle,
  onChartStyle,
  flags,
  onToggle,
  levelCount,
  onAddLevel,
  onClearLevels,
  onResetView,
}: {
  chartStyle: ChartStyle;
  onChartStyle: (style: ChartStyle) => void;
  flags: Record<ToggleKey, boolean>;
  onToggle: (key: ToggleKey) => void;
  levelCount: number;
  onAddLevel: () => void;
  onClearLevels: () => void;
  onResetView: () => void;
}) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {(["candles", "area", "line"] as ChartStyle[]).map((style) => (
        <ToolbarButton
          key={style}
          active={chartStyle === style}
          onClick={() => onChartStyle(style)}
        >
          {style === "candles" ? "Candles" : style === "area" ? "Area" : "Line"}
        </ToolbarButton>
      ))}
      {TOGGLES.map((toggle) => (
        <ToolbarButton
          key={toggle.key}
          active={flags[toggle.key]}
          onClick={() => onToggle(toggle.key)}
        >
          {toggle.label}
        </ToolbarButton>
      ))}
      <button
        type="button"
        onClick={onAddLevel}
        className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-slate-500 hover:bg-slate-900"
      >
        + Level
      </button>
      {levelCount > 0 && (
        <button
          type="button"
          onClick={onClearLevels}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-amber-300 hover:border-amber-500/60 hover:bg-slate-900"
        >
          Clear {levelCount} line{levelCount > 1 ? "s" : ""}
        </button>
      )}
      <button
        type="button"
        onClick={onResetView}
        className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-slate-500 hover:bg-slate-900"
      >
        Reset
      </button>
    </div>
  );
}
