import { useEffect, useRef, useState } from "react";
import { LEGAL_DOCS } from "../lib/legal";
import manifest from "../lib/legalManifest.json";
import { LegalModal } from "./LegalModal";

export function SignupAgreement({ checked, onChange, current }: {
  checked: boolean; onChange: (value: boolean) => void; current: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [openDoc, setOpenDoc] = useState<"terms" | "risk" | "privacy" | null>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  return <section aria-labelledby="signup-agreement-heading" className="space-y-4">
    <h2 ref={heading} tabIndex={-1} id="signup-agreement-heading" className="text-lg font-semibold text-slate-100">Review before creating an account</h2>
    <div id="signup-risk-notice" className="rounded-xl border border-amber-400/40 bg-amber-500/10 p-4 text-sm leading-6 text-amber-100">
      <strong>Investment decisions and losses are your responsibility.</strong> AI Buy/Hold/Sell assessments and scores can be wrong. They are general research, not a personal trading plan, verified profit odds or a guarantee of performance. You can lose all money invested. Verdict does not hold investment funds or execute real-money trades; practice trades use pretend money.
      <p className="mt-2">Liability limitations apply only to the extent permitted by law. Rights that cannot lawfully be waived are preserved.</p>
    </div>
    {LEGAL_DOCS.map(doc => <details key={doc.id} open={doc.id === "terms" ? true : undefined} className="rounded-lg border border-slate-700 bg-slate-950/50 p-3">
      <summary className="cursor-pointer text-sm font-semibold text-slate-200">{doc.title} · {manifest.versions[doc.id]}</summary>
      <div className="mt-3 max-h-64 space-y-4 overflow-y-auto text-xs leading-6 text-slate-400" tabIndex={0} aria-label={`Read ${doc.title}`}>
        {doc.sections.map(section => <section key={section.heading}><h3 className="font-semibold text-slate-200">{section.heading}</h3>{section.body.map(paragraph=><p key={paragraph} className="mt-1">{paragraph}</p>)}</section>)}
      </div>
      <button type="button" onClick={()=>setOpenDoc(doc.id)} className="mt-2 text-xs text-indigo-300 underline">Open {doc.title} in full</button>
    </details>)}
    {!current && <p role="alert" className="text-sm text-rose-300">The legal documents have changed or cannot be verified. Refresh the app before creating an account.</p>}
    <label className="flex items-start gap-3 rounded-lg border border-slate-600 p-3 text-sm leading-6 text-slate-200">
      <input type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)} disabled={!current} aria-describedby="signup-risk-notice" className="mt-1 h-5 w-5 shrink-0 accent-indigo-500" />
      <span>I agree to the Terms of Service, understand the Risk &amp; Data Disclosure, and acknowledge the Privacy Notice. This does not consent to marketing or unrelated data use.</span>
    </label>
    {openDoc && <LegalModal initialDoc={openDoc} onClose={()=>setOpenDoc(null)} />}
  </section>;
}
