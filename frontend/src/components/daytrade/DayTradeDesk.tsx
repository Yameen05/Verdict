import { useCallback, useEffect, useRef, useState } from "react";
import { api, type DayTradeAgentView, type DayTradeSignal } from "../../api/client";

const ACTION_STYLE: Record<string, string> = {
  long: "border-emerald-500/50 bg-emerald-500/10 text-emerald-300",
  short: "border-rose-500/50 bg-rose-500/10 text-rose-300",
  stand_aside: "border-slate-600 bg-slate-800/60 text-slate-300",
};

const VOTE_STYLE: Record<string, string> = {
  long: "text-emerald-300",
  short: "text-rose-300",
  neutral: "text-slate-400",
};

const VOTE_LABEL: Record<string, string> = {
  long: "▲ long",
  short: "▼ short",
  neutral: "— neutral",
};

const SESSION_LABEL: Record<string, string> = {
  open_24_7: "24/7 market",
  premarket: "Pre-market",
  opening_drive: "Opening drive",
  morning: "Mid-morning",
  lunch: "Lunch chop",
  afternoon: "Afternoon",
  power_hour: "Power hour",
  after_hours: "After hours",
  closed: "Closed",
};

function AgentTile({ agent }: { agent: DayTradeAgentView }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-200">{agent.name}</span>
        <span className={`font-mono text-[11px] font-bold ${VOTE_STYLE[agent.vote]}`}>
          {VOTE_LABEL[agent.vote]}
        </span>
      </div>
      <ul className="mt-1.5 space-y-1">
        {agent.reasons.map((r, i) => (
          <li key={i} className="text-[11px] leading-relaxed text-slate-400">
            {r}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PriceStat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className={`mt-0.5 font-mono text-base font-semibold ${tone ?? "text-slate-100"}`}>
        {value}
      </div>
    </div>
  );
}

function PositionSizer({ signal }: { signal: DayTradeSignal }) {
  const [account, setAccount] = useState(10_000);
  const [riskPct, setRiskPct] = useState(1);
  if (signal.risk_per_share === null || signal.entry === null) return null;
  const riskBudget = (account * riskPct) / 100;
  const shares = Math.floor(riskBudget / signal.risk_per_share);
  const cost = shares * signal.entry;
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
      <h4 className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Position size — risk first
      </h4>
      <div className="mt-2 flex flex-wrap items-end gap-3 text-xs">
        <label className="text-slate-400">
          Account $
          <input
            type="number"
            min={100}
            value={account}
            onChange={(e) => setAccount(Math.max(0, Number(e.target.value)))}
            className="mt-1 block w-28 rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
          />
        </label>
        <label className="text-slate-400">
          Risk %
          <input
            type="number"
            min={0.25}
            max={5}
            step={0.25}
            value={riskPct}
            onChange={(e) => setRiskPct(Math.min(5, Math.max(0.25, Number(e.target.value))))}
            className="mt-1 block w-20 rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
          />
        </label>
        <div className="text-slate-300">
          Risking <span className="font-mono text-slate-100">${riskBudget.toFixed(0)}</span> ÷ $
          {signal.risk_per_share.toFixed(2)}/share →{" "}
          <span className="font-mono text-base font-bold text-indigo-300">
            {shares.toLocaleString()} shares
          </span>{" "}
          <span className="text-slate-500">(~${cost.toLocaleString(undefined, { maximumFractionDigits: 0 })})</span>
        </div>
      </div>
      <p className="mt-2 text-[10px] text-slate-500">
        Size from the stop, never from conviction. If the stop hits, you lose ~{riskPct}% — that
        must be survivable ten times in a row.
      </p>
    </div>
  );
}

export function DayTradeDesk({ ticker }: { ticker: string }) {
  const [signal, setSignal] = useState<DayTradeSignal | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [auto, setAuto] = useState(false);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);
  const tickerRef = useRef(ticker);

  const run = useCallback(() => {
    const requested = tickerRef.current;
    setLoading(true);
    setError(null);
    api
      .daytradeSignal(requested)
      .then((s) => {
        if (tickerRef.current === requested) {
          setSignal(s);
          setLastFetch(new Date());
        }
      })
      .catch((e: unknown) => {
        if (tickerRef.current === requested) {
          setError(e instanceof Error ? e.message : "Desk analysis failed");
        }
      })
      .finally(() => {
        if (tickerRef.current === requested) setLoading(false);
      });
  }, []);

  // Reset when the ticker changes; keep auto-refresh running if enabled.
  useEffect(() => {
    tickerRef.current = ticker;
    setSignal(null);
    setError(null);
    setLastFetch(null);
  }, [ticker]);

  useEffect(() => {
    if (!auto) return;
    run();
    const id = window.setInterval(run, 60_000);
    return () => window.clearInterval(id);
  }, [auto, ticker, run]);

  const style = signal ? ACTION_STYLE[signal.action] : ACTION_STYLE.stand_aside;

  return (
    <section className="rounded-3xl border border-slate-800/80 bg-slate-900/50 shadow-xl shadow-slate-950/40">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-5 py-4">
        <div>
          <h2 className="font-display text-xl text-slate-100">The desk</h2>
          <p className="text-[11px] text-slate-500">
            Five agents read the tape — trend, momentum, VWAP, levels, catalyst — and a risk
            manager only signs off with a stop and ≥1.3R. “Stand aside” is a real answer.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setAuto((v) => !v)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
              auto
                ? "border-indigo-500 bg-indigo-500/15 text-indigo-200"
                : "border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200"
            }`}
            title="Re-run the desk every 60 seconds"
          >
            {auto ? "● Auto 60s" : "○ Auto off"}
          </button>
          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="rounded-full bg-indigo-600 px-4 py-1.5 text-xs font-semibold text-white shadow-lg shadow-indigo-950/50 transition hover:bg-indigo-500 disabled:opacity-50"
          >
            {loading ? "Reading the tape…" : signal ? "Re-run desk" : `Analyze ${ticker}`}
          </button>
        </div>
      </header>

      {error && <p className="px-5 py-4 text-sm text-rose-300">{error}</p>}

      {!signal && !error && !loading && (
        <p className="px-5 py-6 text-center text-xs text-slate-500">
          Run the desk to get a live buy / sell / stand-aside call for {ticker} with entry, stop,
          and target.
        </p>
      )}

      {signal && !error && (
        <div className="space-y-5 px-5 py-5">
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`rounded-2xl border px-5 py-2 font-display text-2xl font-medium italic ${style}`}
            >
              {signal.action_label}
            </span>
            <div className="text-xs text-slate-400">
              <div>
                Confidence{" "}
                <span className="font-semibold text-slate-200">{signal.confidence}%</span> ·{" "}
                {signal.source === "llm" ? "AI head trader + desk" : "deterministic desk"}
              </div>
              <div className="mt-0.5">
                <span className="rounded-full border border-slate-700 bg-slate-950/60 px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-400">
                  {SESSION_LABEL[signal.session] ?? signal.session}
                </span>
                <span className="ml-2 text-[11px] text-slate-500">{signal.session_note}</span>
              </div>
            </div>
          </div>

          <p className="text-sm leading-relaxed text-slate-200">{signal.summary}</p>

          {signal.entry !== null && signal.stop !== null && signal.target !== null && (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <PriceStat label="Entry" value={`$${signal.entry.toFixed(2)}`} />
                <PriceStat
                  label="Stop loss"
                  value={`$${signal.stop.toFixed(2)}`}
                  tone="text-rose-300"
                />
                <PriceStat
                  label="Target"
                  value={`$${signal.target.toFixed(2)}`}
                  tone="text-emerald-300"
                />
                <PriceStat
                  label="Risk : reward"
                  value={signal.risk_reward !== null ? `1 : ${signal.risk_reward.toFixed(1)}` : "—"}
                  tone="text-indigo-300"
                />
              </div>
              <PositionSizer signal={signal} />
            </>
          )}

          {signal.plan.length > 0 && (
            <div>
              <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                Execution plan
              </h4>
              <ol className="space-y-1 text-xs text-slate-300">
                {signal.plan.map((p, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="font-display italic text-indigo-400">{i + 1}.</span>
                    <span>{p}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                Why
              </h4>
              <ul className="space-y-1 text-xs text-slate-300">
                {signal.rationale.map((r, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span className="text-emerald-400">▸</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                Risks
              </h4>
              <ul className="space-y-1 text-xs text-slate-300">
                {signal.risks.map((r, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span className="text-rose-400">▸</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div>
            <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
              The desk's votes
            </h4>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
              {signal.agents.map((a) => (
                <AgentTile key={a.name} agent={a} />
              ))}
            </div>
          </div>

          <p className="border-t border-slate-800 pt-3 text-[11px] italic text-slate-500">
            {signal.disclaimer}
            {lastFetch && (
              <span className="not-italic text-slate-600">
                {" "}
                · data as of {signal.as_of} · fetched {lastFetch.toLocaleTimeString()}
              </span>
            )}
          </p>
        </div>
      )}
    </section>
  );
}
