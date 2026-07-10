interface Step {
  label: string;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  {
    label: "01",
    title: "Pick and click",
    body: "Choose a stock or coin, say how long you'd hold it (a week? a year?), and hit Analyze. That's it — official reports, news, prices, and insider trades are gathered for you automatically.",
  },
  {
    label: "02",
    title: "Watch the argument",
    body: "One AI argues FOR buying, another argues AGAINST — using only real evidence. A judge weighs both sides and gives you Buy, Hold, or Sell for YOUR time window, plus what would change its mind.",
  },
  {
    label: "03",
    title: "Keep it honest",
    body: "Ask follow-up questions in plain English, hit “Explain it simply” if anything sounds like finance-speak, and check the scoreboard — it tracks whether past verdicts were actually right.",
  },
];

export function WelcomeHero() {
  return (
    <section className="relative mb-8 overflow-hidden rounded-3xl border border-slate-800/80 bg-slate-900/40 p-6 sm:p-10">
      {/* Oversized serif watermark — pure decoration */}
      <span
        aria-hidden
        className="pointer-events-none absolute -right-6 -top-16 select-none font-display text-[16rem] italic leading-none text-indigo-500/[0.07]"
      >
        V
      </span>

      <div className="relative flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl">
          <span className="inline-flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-indigo-300">
            <span className="h-px w-8 bg-indigo-400/60" />
            Multi-agent stock research
          </span>
          <h1 className="mt-4 font-display text-4xl font-medium tracking-tight text-slate-50 sm:text-5xl">
            Every stock gets a trial.
            <span className="block italic text-indigo-300">
              Bull v. Bear. One verdict.
            </span>
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-slate-300">
            Thinking about a stock or a coin? Pick it, pick how long you'd hold it,
            and press one button. Verdict gathers the real evidence, makes two AIs
            argue both sides, and hands you a clear Buy / Hold / Sell — with a plain-
            English explanation and an honest track record. No finance degree needed.
          </p>
        </div>

        <ol className="grid w-full gap-5 sm:grid-cols-3 lg:max-w-2xl">
          {STEPS.map((s) => (
            <li key={s.label} className="border-t border-slate-700/70 pt-3">
              <div className="flex items-baseline gap-2">
                <span className="font-display text-lg italic text-indigo-400">
                  {s.label}
                </span>
                <span className="text-sm font-semibold text-slate-100">{s.title}</span>
              </div>
              <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
