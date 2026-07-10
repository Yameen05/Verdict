import type { ReactNode } from "react";

export function InfoTip({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <span className="group relative inline-flex align-middle">
      <span
        tabIndex={0}
        aria-label={label}
        title={label}
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-700 bg-slate-950 text-[10px] font-bold text-slate-500 outline-none transition hover:border-cyan-500/70 hover:text-cyan-200 focus:border-cyan-500/70 focus:text-cyan-200"
      >
        i
      </span>
      <span className="pointer-events-none absolute left-0 top-full z-40 mt-2 hidden w-64 max-w-[calc(100vw-3rem)] rounded-md border border-slate-700 bg-slate-950 p-3 text-left shadow-xl shadow-black/10 group-hover:block group-focus-within:block">
        <span className="block text-[11px] leading-relaxed text-slate-300">
          {children}
        </span>
      </span>
    </span>
  );
}
