import { useEffect, useState } from "react";
import { api, type DayTradeScanResponse } from "../../api/client";
import { StockChartPanel } from "../StockChartPanel";
import { DayTradeDesk } from "./DayTradeDesk";

/** Liquid names day traders live in — one click to load. */
const QUICK_TICKERS = [
  "SPY", "QQQ", "TSLA", "NVDA", "AMD", "AAPL", "META", "COIN",
  "PLTR", "HOOD", "MSTR", "BTC-USD", "ETH-USD", "SOL-USD",
] as const;

const SCAN_ACTION_STYLE: Record<string, string> = {
  long: "text-emerald-300",
  short: "text-rose-300",
  stand_aside: "text-slate-400",
};

function Scanner({ onPick }: { onPick: (t: string) => void }) {
  const [scan, setScan] = useState<DayTradeScanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    api
      .daytradeScan()
      .then(setScan)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Scan failed"))
      .finally(() => setLoading(false));
  }

  return (
    <section className="rounded-3xl border border-slate-800/80 bg-slate-900/50 p-5 shadow-xl shadow-slate-950/40">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-xl text-slate-100">Scanner</h2>
          <p className="text-[11px] text-slate-500">
            Rules-only sweep of the liquid names, strongest desk score first. Click one to load
            the full five-agent analysis.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="rounded-full border border-cyan-500/60 bg-cyan-500/10 px-4 py-1.5 text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/20 disabled:opacity-50"
        >
          {loading ? "Sweeping…" : scan ? "Re-scan" : "Scan the market"}
        </button>
      </div>

      {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}

      {scan && !error && (
        <>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {scan.rows.map((row) => (
              <button
                key={row.ticker}
                type="button"
                onClick={() => onPick(row.ticker)}
                className="group rounded-xl border border-slate-800 bg-slate-950/50 px-3 py-2.5 text-left transition hover:border-indigo-500/60 hover:bg-slate-900"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-sm font-bold text-slate-100">{row.ticker}</span>
                  <span
                    className={`text-[11px] font-semibold ${SCAN_ACTION_STYLE[row.action]}`}
                  >
                    {row.action === "long" ? "▲" : row.action === "short" ? "▼" : "—"}{" "}
                    {row.action_label}
                  </span>
                </div>
                <div className="mt-0.5 flex items-baseline justify-between gap-2">
                  <span className="truncate text-[11px] text-slate-500">{row.note}</span>
                  <span className="shrink-0 font-mono text-[11px] text-slate-400">
                    ${row.close.toFixed(2)}
                  </span>
                </div>
              </button>
            ))}
          </div>
          {scan.skipped.length > 0 && (
            <p className="mt-2 text-[10px] text-slate-600">
              No data right now for: {scan.skipped.join(", ")}
            </p>
          )}
        </>
      )}
    </section>
  );
}

export function DayTradePage() {
  const [ticker, setTicker] = useState("SPY");
  const [search, setSearch] = useState("");

  function applySearch() {
    const t = search.trim().toUpperCase();
    if (t) {
      setTicker(t);
      setSearch("");
    }
  }

  // Surface the page at the top when a ticker is picked from the scanner.
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [ticker]);

  return (
    <div className="space-y-6">
      <section className="rounded-3xl border border-slate-800/80 bg-slate-900/50 p-5 shadow-xl shadow-slate-950/40 sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <span className="inline-flex items-center gap-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-indigo-300">
              <span className="h-px w-8 bg-indigo-400/60" />
              Intraday desk
            </span>
            <h1 className="mt-2 font-display text-3xl font-medium tracking-tight text-slate-50">
              Day trading
            </h1>
            <p className="mt-1 max-w-xl text-xs leading-relaxed text-slate-400">
              Any symbol, analyzed live: five desk agents vote on the tape, and a risk manager
              issues buy / sell / stand aside with an entry, a stop, and a target — or refuses
              the trade. Most of the day the honest answer is “stand aside”.
            </p>
          </div>
          <div className="w-full max-w-sm">
            <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-400">
              Search any ticker
            </label>
            <div className="flex gap-2">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === "Enter" && applySearch()}
                placeholder="e.g. TSLA, GME, BTC-USD…"
                className="flex-1 rounded-full border border-slate-700 bg-slate-950 px-4 py-2 font-mono text-sm uppercase placeholder-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                type="button"
                onClick={applySearch}
                disabled={!search.trim()}
                className="rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-50"
              >
                Load
              </button>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          {QUICK_TICKERS.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTicker(t)}
              className={`rounded-full border px-2.5 py-1 font-mono text-[11px] font-semibold transition ${
                ticker === t
                  ? "border-indigo-500 bg-indigo-500/15 text-indigo-200"
                  : "border-slate-800 bg-slate-950/40 text-slate-400 hover:border-slate-600 hover:text-slate-200"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-3xl border border-slate-800/80 bg-slate-900/50 p-5 shadow-xl shadow-slate-950/40">
        <StockChartPanel ticker={ticker} />
      </section>

      <DayTradeDesk ticker={ticker} />

      <Scanner onPick={setTicker} />

      <p className="text-center text-[11px] text-slate-500">
        Prices come from Yahoo Finance and can lag by a minute or more — always confirm the live
        quote with your broker before entering. Day trading is high-risk; most retail day traders
        lose money.
      </p>
    </div>
  );
}
