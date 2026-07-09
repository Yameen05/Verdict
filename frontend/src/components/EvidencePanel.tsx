import type { EvidenceItem } from "../api/client";

const SOURCE_STYLE: Record<EvidenceItem["source"], { label: string; chip: string }> = {
  sec: { label: "SEC filing", chip: "bg-indigo-500/15 text-indigo-300" },
  news: { label: "News", chip: "bg-cyan-500/15 text-cyan-300" },
  metrics: { label: "Financials", chip: "bg-emerald-500/15 text-emerald-300" },
  insider: { label: "Insiders", chip: "bg-amber-500/15 text-amber-300" },
  signals: { label: "Signals", chip: "bg-fuchsia-500/15 text-fuchsia-300" },
};

export function EvidencePanel({ evidence }: { evidence: EvidenceItem[] }) {
  if (evidence.length === 0) return null;

  return (
    <details className="mt-6 rounded-xl border border-slate-800 bg-slate-900/50">
      <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-slate-200 hover:text-white">
        Evidence ledger{" "}
        <span className="font-normal text-slate-500">
          — every fact the debate could cite ({evidence.length} items)
        </span>
      </summary>
      <ul className="divide-y divide-slate-800/80 px-4 pb-3">
        {evidence.map((e) => {
          const src = SOURCE_STYLE[e.source];
          return (
            <li key={e.id} className="flex gap-3 py-2.5 text-xs">
              <span className="w-20 shrink-0 font-mono text-[10px] text-slate-500">{e.id}</span>
              <span
                className={`h-fit shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide ${src.chip}`}
              >
                {src.label}
              </span>
              <div className="min-w-0">
                <div className="font-medium text-slate-300">{e.label}</div>
                <div className="text-slate-400">
                  {e.content}
                  {e.url && (
                    <a
                      href={e.url}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-1 text-indigo-400 hover:underline"
                    >
                      ↗
                    </a>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </details>
  );
}
