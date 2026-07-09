import { useState } from "react";
import { api, type TimingAction, type TimingAssessment } from "../../api/client";

const ACTION_STYLE: Record<TimingAction, string> = {
  buy_now: "border-emerald-500/50 bg-emerald-500/10 text-emerald-300",
  accumulate: "border-sky-500/50 bg-sky-500/10 text-sky-300",
  wait_pullback: "border-amber-500/50 bg-amber-500/10 text-amber-300",
  wait_watch: "border-slate-600 bg-slate-800/60 text-slate-300",
  avoid: "border-rose-500/50 bg-rose-500/10 text-rose-300",
};

const ACTION_HELP: Record<TimingAction, { title: string; body: string }> = {
  buy_now: {
    title: "Buy now",
    body: "The setup looks good enough to enter now for the selected time window. It does not mean guaranteed profit.",
  },
  accumulate: {
    title: "Accumulate gradually",
    body: "Do not put all the money in at once. Split the buy into smaller chunks so a bad entry hurts less.",
  },
  wait_pullback: {
    title: "Wait for a pullback",
    body: "The stock may be worth watching, but the current price looks stretched. Wait for a dip toward a better entry zone.",
  },
  wait_watch: {
    title: "Wait and watch",
    body: "The signals are mixed or unclear. Staying out for now is cleaner than forcing a trade.",
  },
  avoid: {
    title: "Avoid for now",
    body: "The current setup looks weak or too risky. Do not buy unless the chart, news, or fundamentals improve.",
  },
};

const HORIZONS: { days: number; label: string }[] = [
  { days: 7, label: "1 week" },
  { days: 14, label: "2 weeks" },
  { days: 30, label: "1 month" },
  { days: 90, label: "3 months" },
];

function Tech({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-0.5 text-sm font-medium text-slate-200">{value}</div>
    </div>
  );
}

function fmtNum(v: unknown, suffix = ""): string {
  return typeof v === "number" ? `${v}${suffix}` : "—";
}

function ActionHelpIcon({ action }: { action: TimingAction }) {
  const help = ACTION_HELP[action];
  return (
    <span className="group relative inline-flex">
      <span
        tabIndex={0}
        role="img"
        aria-label={`${help.title}: ${help.body}`}
        title={`${help.title}: ${help.body}`}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-xs font-bold text-slate-300 outline-none transition hover:border-cyan-500/70 hover:text-cyan-200 focus:border-cyan-500/70 focus:text-cyan-200"
      >
        i
      </span>
      <span className="pointer-events-none absolute left-0 top-full z-30 mt-2 hidden w-72 max-w-[calc(100vw-3rem)] rounded-md border border-slate-700 bg-slate-950 p-3 text-left shadow-xl shadow-black/40 group-hover:block group-focus-within:block">
        <span className="block text-xs font-semibold text-slate-100">{help.title}</span>
        <span className="mt-1 block text-[11px] leading-relaxed text-slate-400">
          {help.body}
        </span>
      </span>
    </span>
  );
}

export function TimingPanel({ ticker }: { ticker: string }) {
  const [horizon, setHorizon] = useState(14);
  const [data, setData] = useState<TimingAssessment | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function run(days: number) {
    setHorizon(days);
    setLoading(true);
    setError(null);
    api
      .timing(ticker, days)
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Timing assessment failed"),
      )
      .finally(() => setLoading(false));
  }

  const t = data?.technicals ?? {};

  return (
    <section className="mt-4 rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Timing agent</h3>
          <p className="text-[11px] text-slate-500">
            Reads the chart + news and suggests whether to buy now, wait, or accumulate.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex overflow-hidden rounded-md border border-slate-800">
            {HORIZONS.map((h) => (
              <button
                key={h.days}
                type="button"
                onClick={() => (data || loading ? run(h.days) : setHorizon(h.days))}
                className={`px-2.5 py-1 text-xs font-semibold transition ${
                  horizon === h.days
                    ? "bg-slate-100 text-slate-950"
                    : "bg-slate-900 text-slate-400 hover:text-slate-100"
                }`}
              >
                {h.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => run(horizon)}
            disabled={loading}
            className="rounded-md border border-cyan-500/60 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
          >
            {loading ? "Analyzing…" : data ? "Re-assess" : `Should I buy ${ticker}?`}
          </button>
        </div>
      </header>

      {error && <p className="px-4 py-3 text-sm text-rose-300">{error}</p>}

      {data && !error && (
        <div className="space-y-4 px-4 py-4">
          <div className="flex flex-wrap items-center gap-3">
            <ActionHelpIcon action={data.action} />
            <span
              className={`rounded-lg border px-3 py-1.5 text-sm font-bold ${ACTION_STYLE[data.action]}`}
            >
              {data.action_label}
            </span>
            <span className="text-xs text-slate-400">
              Confidence <span className="font-semibold text-slate-200">{data.confidence}%</span>
            </span>
            <span className="text-xs text-slate-500">
              · {data.horizon_days}-day horizon · {data.source === "llm" ? "AI + technicals" : "rules + technicals"}
            </span>
          </div>

          <p className="text-sm text-slate-200">{data.summary}</p>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Why
              </div>
              <ul className="space-y-1 text-xs text-slate-300">
                {data.rationale.map((r, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span className="text-emerald-400">▸</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Risks
              </div>
              <ul className="space-y-1 text-xs text-slate-300">
                {data.risks.map((r, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span className="text-rose-400">▸</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <Tech label="Trend" value={String(t.trend ?? "—")} />
            <Tech label="RSI (14)" value={fmtNum(t.rsi14)} />
            <Tech label="20d move" value={fmtNum(t.momentum_20d_pct, "%")} />
            <Tech label="Volatility" value={fmtNum(t.volatility_pct, "%/day")} />
            <Tech
              label="Entry zone"
              value={
                data.entry_zone_low != null && data.entry_zone_high != null
                  ? `$${data.entry_zone_low.toFixed(2)}–$${data.entry_zone_high.toFixed(2)}`
                  : "—"
              }
            />
          </div>

          {data.headlines.length > 0 && (
            <div>
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Headlines considered
              </div>
              <ul className="space-y-1 text-xs text-slate-400">
                {data.headlines.slice(0, 4).map((h, i) => (
                  <li key={i} className="truncate">• {h}</li>
                ))}
              </ul>
            </div>
          )}

          <p className="border-t border-slate-800 pt-3 text-[11px] italic text-slate-500">
            {data.disclaimer}
          </p>
        </div>
      )}
    </section>
  );
}
