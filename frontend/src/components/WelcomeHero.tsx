interface Step {
  label: string;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  {
    label: "01",
    title: "Pick a stock",
    body: "Choose from popular tickers or paste your own. Optionally ingest the latest 10-K / 10-Q so the agents can read the actual filing.",
  },
  {
    label: "02",
    title: "Run the research",
    body: "Three agents work in parallel: SEC filings (RAG), news sentiment (last 30 days), and live financial metrics. A synthesizer turns it into a Buy / Hold / Sell.",
  },
  {
    label: "03",
    title: "Ask follow-ups",
    body: "Chat with an analyst grounded in the report you just produced. Hypotheticals like “if I invest $1,000” use the metrics already on screen — no hallucinated prices.",
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
            One ticker. Three agents.
            <span className="block text-indigo-300">A grounded second opinion.</span>
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-300">
            Verdict reads the company’s SEC filing, scans the last 30 days of news,
            pulls live financials, and produces a transparent Buy / Hold / Sell with
            citations. Then you can ask follow-up questions in plain English.
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
