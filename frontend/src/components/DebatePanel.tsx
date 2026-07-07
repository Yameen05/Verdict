import { useMemo, useState } from "react";
import type { DebateCase, EvidenceItem } from "../api/client";

const STANCE = {
  bull: {
    title: "The Bull Case",
    icon: "▲",
    accent: "text-emerald-400",
    border: "border-emerald-500/25",
    chip: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20",
  },
  bear: {
    title: "The Bear Case",
    icon: "▼",
    accent: "text-rose-400",
    border: "border-rose-500/25",
    chip: "border-rose-500/30 bg-rose-500/10 text-rose-300 hover:bg-rose-500/20",
  },
} as const;

function CaseColumn({
  side,
  data,
  evidenceById,
  live,
}: {
  side: "bull" | "bear";
  data: DebateCase | null;
  evidenceById: Map<string, EvidenceItem>;
  live: boolean;
}) {
  const s = STANCE[side];
  const [openEvidence, setOpenEvidence] = useState<string | null>(null);

  return (
    <div className={`rounded-xl border ${s.border} bg-slate-900/70 p-4`}>
      <h3 className={`mb-2 flex items-center gap-2 text-sm font-semibold ${s.accent}`}>
        <span>{s.icon}</span> {s.title}
        {live && !data && (
          <span className="ml-auto animate-pulse text-[10px] font-normal text-slate-500">
            arguing…
          </span>
        )}
      </h3>

      {!data && !live && (
        <p className="text-xs text-slate-500">No case was argued.</p>
      )}
      {data && data.status !== "ok" && (
        <p className="text-xs text-slate-500">{data.error ?? "Advocate unavailable."}</p>
      )}
      {data && data.status === "ok" && (
        <>
          <p className="mb-3 text-xs font-medium italic leading-relaxed text-slate-200">
            “{data.thesis}”
          </p>
          <ul className="space-y-2.5">
            {data.arguments.map((arg, i) => (
              <li key={i} className="text-xs leading-relaxed text-slate-300">
                <span>{arg.claim}</span>
                <span className="ml-1.5 inline-flex flex-wrap gap-1 align-middle">
                  {arg.evidence.map((id) => (
                    <button
                      key={id}
                      onClick={() => setOpenEvidence(openEvidence === `${i}:${id}` ? null : `${i}:${id}`)}
                      className={`rounded border px-1 py-px font-mono text-[9px] transition ${s.chip}`}
                      title="Show the cited evidence"
                    >
                      {id}
                    </button>
                  ))}
                </span>
                {arg.evidence.map((id) => {
                  if (openEvidence !== `${i}:${id}`) return null;
                  const ev = evidenceById.get(id);
                  return (
                    <blockquote
                      key={id}
                      className="mt-1.5 rounded-md border-l-2 border-slate-600 bg-slate-950/70 px-2.5 py-1.5 text-[11px] text-slate-400"
                    >
                      <span className="mb-0.5 block font-medium text-slate-300">
                        {ev?.label ?? id}
                      </span>
                      {ev?.content ?? "Evidence not found in the ledger."}
                      {ev?.url && (
                        <a
                          href={ev.url}
                          target="_blank"
                          rel="noreferrer"
                          className="ml-1 text-indigo-400 hover:underline"
                        >
                          source ↗
                        </a>
                      )}
                    </blockquote>
                  );
                })}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

interface Props {
  bull: DebateCase | null;
  bear: DebateCase | null;
  evidence: EvidenceItem[];
  live: boolean; // streaming still in progress
}

export function DebatePanel({ bull, bear, evidence, live }: Props) {
  const evidenceById = useMemo(
    () => new Map(evidence.map((e) => [e.id, e])),
    [evidence],
  );

  if (!bull && !bear && !live) return null;

  return (
    <section className="mt-6">
      <h2 className="mb-3 text-sm font-semibold text-slate-200">
        The debate{" "}
        <span className="font-normal text-slate-500">
          — two advocates, one evidence ledger; click a citation to see the source
        </span>
      </h2>
      <div className="grid gap-4 md:grid-cols-2">
        <CaseColumn side="bull" data={bull} evidenceById={evidenceById} live={live} />
        <CaseColumn side="bear" data={bear} evidenceById={evidenceById} live={live} />
      </div>
    </section>
  );
}
