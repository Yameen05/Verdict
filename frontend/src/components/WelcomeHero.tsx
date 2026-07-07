interface Step {
  label: string;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  {
    label: "01",
    title: "Gather the evidence",
    body: "Four agents work in parallel: SEC filings (RAG), news sentiment, live financials, and insider Form 4 activity — every fact lands in a citable evidence ledger.",
  },
  {
    label: "02",
    title: "Hold the trial",
    body: "A bull advocate and a bear advocate each argue their strongest case from the same ledger. A judge weighs both, issues the verdict with a confidence score, and states what would change its mind.",
  },
  {
    label: "03",
    title: "Check the record",
    body: "Ask follow-up questions grounded in the report (the analyst can search the filing live), and watch the scoreboard grade every past verdict against what the stock actually did.",
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
            Verdict collects the evidence — SEC filings, news, financials, insider
            trades — then makes a bull and a bear advocate argue over it. A judge
            issues the call with a confidence score, cited evidence, and the
            conditions that would flip it. The scoreboard tracks whether it was right.
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
