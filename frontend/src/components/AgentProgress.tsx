import { type ReactNode } from "react";

export type AgentKey =
  | "sec_agent"
  | "news_agent"
  | "metrics_agent"
  | "insider_agent"
  | "bull_agent"
  | "bear_agent"
  | "judge";

export interface AgentState {
  status: "idle" | "running" | "done" | "error";
  summary?: string;
}

interface Props {
  states: Record<AgentKey, AgentState>;
}

const EVIDENCE_ROW: { key: AgentKey; label: string }[] = [
  { key: "sec_agent", label: "SEC filings" },
  { key: "news_agent", label: "News & sentiment" },
  { key: "metrics_agent", label: "Financials" },
  { key: "insider_agent", label: "Insider activity" },
];

const TRIAL_ROW: { key: AgentKey; label: string }[] = [
  { key: "bull_agent", label: "Bull advocate" },
  { key: "bear_agent", label: "Bear advocate" },
  { key: "judge", label: "The judge" },
];

const DOT: Record<AgentState["status"], { color: string; pulse: boolean; label: string }> = {
  idle: { color: "bg-slate-700", pulse: false, label: "waiting" },
  running: { color: "bg-indigo-400", pulse: true, label: "running" },
  done: { color: "bg-emerald-500", pulse: false, label: "done" },
  error: { color: "bg-rose-500", pulse: false, label: "error" },
};

function Tile({ label, state }: { label: string; state: AgentState }) {
  const dot = DOT[state.status];
  return (
    <div className="flex items-center gap-3 rounded-md border border-slate-800 bg-slate-900/60 px-3 py-2">
      <span
        className={`inline-block h-2.5 w-2.5 rounded-full ${dot.color} ${
          dot.pulse ? "animate-pulse" : ""
        }`}
        aria-label={dot.label}
      />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium text-slate-200">{label}</div>
        <div className="truncate text-[11px] text-slate-500">{state.summary ?? dot.label}</div>
      </div>
    </div>
  );
}

export function AgentProgress({ states }: Props) {
  return (
    <div className="space-y-2">
      <div>
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
          Gathering evidence
        </div>
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-4">
          {EVIDENCE_ROW.map(({ key, label }) => (
            <Tile key={key} label={label} state={states[key]} />
          ))}
        </div>
      </div>
      <div>
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
          The trial
        </div>
        <div className="grid gap-2 md:grid-cols-3">
          {TRIAL_ROW.map(({ key, label }) => (
            <Tile key={key} label={label} state={states[key]} />
          ))}
        </div>
      </div>
    </div>
  );
}

export function StatusLine({ children }: { children: ReactNode }) {
  return <p className="text-xs text-slate-400">{children}</p>;
}
