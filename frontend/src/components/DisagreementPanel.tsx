import type { ResearchResponse, TimingAssessment } from "../api/client";
import { buildDisagreements } from "../lib/disagreements";
import { InfoTip } from "./InfoTip";

export function DisagreementPanel({
  research,
  timing,
}: {
  research: ResearchResponse | null;
  timing: TimingAssessment | null;
}) {
  const disagreements = buildDisagreements(research, timing);
  if (!research || disagreements.length === 0) return null;

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
      <h3 className="text-sm font-semibold text-slate-100">
        Signals disagree
        <InfoTip label="Signals disagree">
          Mixed signals are normal. This section shows which important source is
          pushing against the final call so you know what to watch.
        </InfoTip>
      </h3>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {disagreements.map((d) => (
          <div
            key={d.title}
            className={`rounded-lg border p-3 ${
              d.severity === "important"
                ? "border-amber-500/30 bg-amber-500/10"
                : "border-slate-800 bg-slate-900/60"
            }`}
          >
            <div className="text-xs font-semibold text-slate-100">{d.title}</div>
            <p className="mt-1 text-xs leading-relaxed text-slate-400">{d.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
