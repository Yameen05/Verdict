import type { ReactNode } from "react";
import type { Evaluation } from "../../api/practice";
import { checkSummary } from "../../lib/practiceGuide";

export const panel =
  "rounded-2xl border border-slate-800 bg-slate-900/50 p-5 sm:p-6";
export const input =
  "w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-indigo-400 focus:outline-hidden";
export const button =
  "rounded-xl border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:border-indigo-400 disabled:opacity-40";
export const primary = `${button} border-indigo-500 bg-indigo-600 text-white hover:bg-indigo-500`;
export const money = (value: number | null | undefined) =>
  value == null
    ? "Waiting for prices"
    : value.toLocaleString(undefined, { style: "currency", currency: "USD" });
export const asOf = (value: string) => value.slice(0, 10);
export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1.5 text-sm text-slate-300">
      <span className="block">{label}</span>
      {children}
      {hint && (
        <span className="block text-xs leading-5 text-slate-400">{hint}</span>
      )}
    </label>
  );
}
export function Checks({ evaluation }: { evaluation: Evaluation }) {
  return (
    <div className="space-y-3">
      <ul className="space-y-2 text-sm leading-6 text-slate-300">
        {evaluation.checks.map((check) => (
          <li key={check.label} className="flex gap-2">
            <span
              className={check.passed ? "text-emerald-300" : "text-amber-300"}
              aria-label={check.passed ? "Fits" : "Does not fit"}
            >
              {check.passed ? "✓" : "–"}
            </span>
            <span>{checkSummary(check)}</span>
          </li>
        ))}
      </ul>
      <details>
        <summary className="cursor-pointer text-xs text-slate-400">
          See the numbers (optional)
        </summary>
        <p className="mt-2 text-xs text-slate-400">
          {evaluation.rules_passed} of {evaluation.rules_total} checks fit. This
          counts conditions, not your chance of making money.
        </p>
        <ul className="mt-2 space-y-2 text-xs leading-5 text-slate-400">
          {evaluation.checks.map((check) => (
            <li key={check.label}>{check.explanation}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
export function PriceNote() {
  return (
    <p className="text-xs leading-6 text-slate-400">
      Prices are from a recent trading day's finish, not live. We leave out
      today. Practice buying and selling use that recorded price.
    </p>
  );
}
