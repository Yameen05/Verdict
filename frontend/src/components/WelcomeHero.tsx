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
    <section className="mb-8 overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-br from-indigo-950/40 via-slate-900 to-slate-950 p-6 sm:p-8">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-2xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-indigo-300">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400" />
            Multi-agent stock research
          </span>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-50 sm:text-4xl">
            Every stock gets a trial.
            <span className="block text-indigo-300">Bull vs. bear. One verdict.</span>
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-300">
            Thinking about a stock or a coin? Pick it, pick how long you'd hold it,
            and press one button. Verdict gathers the real evidence, makes two AIs
            argue both sides, and hands you a clear Buy / Hold / Sell — with a plain-
            English explanation and an honest track record. No finance degree needed.
          </p>
        </div>

        <ul className="grid w-full gap-3 sm:grid-cols-3 lg:max-w-2xl">
          {STEPS.map((s) => (
            <li
              key={s.label}
              className="rounded-xl border border-slate-800 bg-slate-950/60 p-4"
            >
              <div className="mb-2 font-mono text-[10px] tracking-widest text-indigo-300">
                {s.label}
              </div>
              <div className="text-sm font-medium text-slate-100">{s.title}</div>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">{s.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
