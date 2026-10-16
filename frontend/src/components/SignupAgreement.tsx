import { useState } from "react";
import { LegalModal } from "./LegalModal";

interface Props {
  checked: boolean;
  onChange: (value: boolean) => void;
  current: boolean;
}

/** Compact signup consent; complete versioned documents stay in the modal. */
export function SignupAgreement({ checked, onChange, current }: Props) {
  const [openDoc, setOpenDoc] = useState<"terms" | "risk" | "privacy" | null>(null);
  const linkClass = "rounded-sm text-slate-200 underline decoration-slate-500 underline-offset-2 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-indigo-400";

  return (
    <section aria-label="Account agreement" className="space-y-3 border-t border-slate-800 pt-4">
      <p id="signup-risk-notice" className="text-xs leading-5 text-slate-300">
        AI research can be wrong. Scores aren’t verified profit odds. Investing carries risk of loss;
        liability limits apply only as law permits.
      </p>
      <div className="flex items-start gap-3">
        <input id="signup-agreement" type="checkbox" checked={checked}
          onChange={event => onChange(event.target.checked)} disabled={!current}
          aria-describedby="signup-risk-notice signup-consent-purpose"
          className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-indigo-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-indigo-400 disabled:cursor-not-allowed" />
        <div className="min-w-0 text-xs leading-5 text-slate-300">
          <label htmlFor="signup-agreement" className="cursor-pointer">
            I agree to the Terms, understand the investment risks and acknowledge the Privacy Notice.
          </label>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
            <button type="button" className={linkClass} onClick={() => setOpenDoc("terms")}>Terms of Service</button>
            <button type="button" className={linkClass} onClick={() => setOpenDoc("risk")}>Risk Disclosure</button>
            <button type="button" className={linkClass} onClick={() => setOpenDoc("privacy")}>Privacy Notice</button>
          </div>
          <p id="signup-consent-purpose" className="mt-1 text-[11px] text-slate-400">No marketing or unrelated data-use consent.</p>
        </div>
      </div>
      {!current && (
        <p role="alert" className="text-xs leading-5 text-rose-300">The documents have changed or cannot be verified. Refresh the app before creating an account.</p>
      )}
      {openDoc && <LegalModal initialDoc={openDoc} onClose={() => setOpenDoc(null)} />}
    </section>
  );
}
