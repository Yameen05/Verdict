import { useEffect, useState } from "react";
import { LEGAL_DOCS, type LegalDoc } from "../lib/legal";

interface Props {
  initialDoc?: LegalDoc["id"];
  onClose: () => void;
}

/** Overlay with the Risk & Data Disclosure, Terms of Use, and Privacy Policy. */
export function LegalModal({ initialDoc = "risk", onClose }: Props) {
  const [docId, setDocId] = useState<LegalDoc["id"]>(initialDoc);
  const doc = LEGAL_DOCS.find((d) => d.id === docId) ?? LEGAL_DOCS[0];

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/80 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={doc.title}
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl shadow-slate-950/60"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-5 py-3">
          <div className="flex rounded-full border border-slate-800 bg-slate-950/60 p-1 text-xs">
            {LEGAL_DOCS.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => setDocId(d.id)}
                className={`rounded-full px-3 py-1.5 font-medium transition ${
                  d.id === docId
                    ? "bg-slate-100 text-slate-950"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full border border-slate-800 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-600 hover:text-slate-100"
          >
            Close
          </button>
        </div>
        <div className="overflow-y-auto px-6 py-5">
          <h2 className="font-display text-xl font-medium tracking-tight text-slate-50">
            {doc.title}
          </h2>
          <p className="mt-1 text-[11px] uppercase tracking-wide text-slate-500">
            Last updated {doc.updated}
          </p>
          {doc.sections.map((section) => (
            <section key={section.heading} className="mt-5">
              <h3 className="text-sm font-semibold text-slate-200">{section.heading}</h3>
              {section.body.map((paragraph) => (
                <p
                  key={paragraph.slice(0, 40)}
                  className="mt-2 text-xs leading-relaxed text-slate-400"
                >
                  {paragraph}
                </p>
              ))}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
