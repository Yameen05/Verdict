import type { ReactNode } from "react";
import type { PriceInterval, PriceRange } from "../../api/client";
import { fmtMoney, fmtSigned, fmtSignedPct } from "./chartMath";

export const RANGE_OPTIONS: { value: PriceRange; label: string }[] = [
  { value: "1D", label: "1D" },
  { value: "5D", label: "5D" },
  { value: "1M", label: "1M" },
  { value: "3M", label: "3M" },
  { value: "6M", label: "6M" },
  { value: "1Y", label: "1Y" },
  { value: "5Y", label: "5Y" },
];

export const INTERVAL_OPTIONS: { value: PriceInterval; label: string }[] = [
  { value: "1M", label: "1m" },
  { value: "5M", label: "5m" },
  { value: "15M", label: "15m" },
  { value: "1H", label: "1h" },
  { value: "1D", label: "1D" },
  { value: "1W", label: "1W" },
];

export function ChartHeaderInfo({
  ticker,
  lastClose,
  change,
  changePct,
  displayedInterval,
  requestedInterval,
  lastUpdated,
}: {
  ticker: string;
  lastClose: number | null;
  change: number | null;
  changePct: number | null;
  displayedInterval: string;
  requestedInterval: string;
  lastUpdated: string | null;
}) {
  const changeClass =
    change !== null && change >= 0 ? "text-emerald-300" : "text-rose-300";
  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="font-mono text-2xl font-semibold text-slate-100">{ticker}</h2>
        {lastClose !== null && change !== null && changePct !== null && (
          <>
            <span className="text-2xl font-semibold text-slate-100">{fmtMoney(lastClose)}</span>
            <span className={`text-sm font-semibold ${changeClass}`}>
              {fmtSigned(change)} ({fmtSignedPct(changePct)})
            </span>
          </>
        )}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span>Yahoo Finance</span>
        <span>·</span>
        <span>{displayedInterval.toLowerCase()} bars</span>
        {displayedInterval !== requestedInterval && (
          <>
            <span>·</span>
            <span>using {displayedInterval.toLowerCase()}</span>
          </>
        )}
        {lastUpdated && (
          <>
            <span>·</span>
            <span>
              updated{" "}
              {new Date(lastUpdated).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex rounded-md border border-slate-800 bg-slate-900 p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`rounded px-2.5 py-1.5 text-xs font-semibold transition ${
            value === option.value
              ? "bg-slate-100 text-slate-950"
              : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function ToolbarButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border px-3 py-1.5 text-xs font-medium transition ${
        active
          ? "border-cyan-500/60 bg-cyan-500/10 text-cyan-200"
          : "border-slate-700 text-slate-400 hover:border-slate-500 hover:bg-slate-900 hover:text-slate-100"
      }`}
    >
      {children}
    </button>
  );
}

export function Readout({
  label,
  value,
  valueClass = "text-slate-200",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="border-r border-slate-800 px-3 py-2 last:border-r-0">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600">
        {label}
      </div>
      <div className={`mt-0.5 truncate font-medium ${valueClass}`}>{value}</div>
    </div>
  );
}
