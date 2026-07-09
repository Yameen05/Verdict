import { useState } from "react";

export interface StockOption {
  ticker: string;
  name: string;
  sector: string;
}

export const POPULAR_STOCKS: StockOption[] = [
  { ticker: "AAPL", name: "Apple", sector: "Technology" },
  { ticker: "MSFT", name: "Microsoft", sector: "Technology" },
  { ticker: "NVDA", name: "NVIDIA", sector: "Semiconductors" },
  { ticker: "AMD", name: "AMD", sector: "Semiconductors" },
  { ticker: "GOOGL", name: "Alphabet", sector: "Communication" },
  { ticker: "AMZN", name: "Amazon", sector: "Consumer" },
  { ticker: "META", name: "Meta Platforms", sector: "Communication" },
  { ticker: "TSLA", name: "Tesla", sector: "Auto" },
  { ticker: "F", name: "Ford", sector: "Auto" },
  { ticker: "NFLX", name: "Netflix", sector: "Communication" },
  { ticker: "DIS", name: "Disney", sector: "Communication" },
  { ticker: "PLTR", name: "Palantir", sector: "Technology" },
  { ticker: "COIN", name: "Coinbase", sector: "Financials" },
  { ticker: "JPM", name: "JPMorgan Chase", sector: "Financials" },
  { ticker: "V", name: "Visa", sector: "Financials" },
  { ticker: "BAC", name: "Bank of America", sector: "Financials" },
  { ticker: "WMT", name: "Walmart", sector: "Consumer" },
  { ticker: "COST", name: "Costco", sector: "Consumer" },
  { ticker: "NKE", name: "Nike", sector: "Consumer" },
  { ticker: "SBUX", name: "Starbucks", sector: "Consumer" },
  { ticker: "KO", name: "Coca-Cola", sector: "Consumer" },
  { ticker: "MCD", name: "McDonald's", sector: "Consumer" },
  { ticker: "JNJ", name: "Johnson & Johnson", sector: "Healthcare" },
  { ticker: "UNH", name: "UnitedHealth", sector: "Healthcare" },
  { ticker: "PFE", name: "Pfizer", sector: "Healthcare" },
  { ticker: "XOM", name: "ExxonMobil", sector: "Energy" },
  { ticker: "CVX", name: "Chevron", sector: "Energy" },
  { ticker: "BA", name: "Boeing", sector: "Industrials" },
  // Crypto trades 24/7; SEC-filing and insider evidence don't apply to coins.
  { ticker: "BTC-USD", name: "Bitcoin", sector: "Crypto" },
  { ticker: "ETH-USD", name: "Ethereum", sector: "Crypto" },
  { ticker: "SOL-USD", name: "Solana", sector: "Crypto" },
  { ticker: "XRP-USD", name: "XRP", sector: "Crypto" },
  { ticker: "DOGE-USD", name: "Dogecoin", sector: "Crypto" },
  { ticker: "ADA-USD", name: "Cardano", sector: "Crypto" },
];

interface Props {
  ticker: string;
  setTicker: (t: string) => void;
}

export function StockPicker({ ticker, setTicker }: Props) {
  const [custom, setCustom] = useState("");
  const [filter, setFilter] = useState("");

  const filtered = filter
    ? POPULAR_STOCKS.filter(
        (s) =>
          s.ticker.toLowerCase().includes(filter.toLowerCase()) ||
          s.name.toLowerCase().includes(filter.toLowerCase()) ||
          s.sector.toLowerCase().includes(filter.toLowerCase()),
      )
    : POPULAR_STOCKS;

  function applyCustom() {
    const t = custom.trim().toUpperCase();
    if (t) {
      setTicker(t);
      setCustom("");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px]">
          <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-slate-400">
            Search
          </label>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Type a name — Apple, Bitcoin, Nike…"
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm placeholder-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between text-xs">
          <span className="font-medium uppercase tracking-wider text-slate-400">
            Pick a stock or coin
          </span>
          <span className="text-slate-500">
            Selected:{" "}
            <span className="font-mono font-semibold text-indigo-300">{ticker || "—"}</span>
          </span>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {filtered.map((s) => {
            const active = s.ticker === ticker;
            return (
              <button
                key={s.ticker}
                onClick={() => setTicker(s.ticker)}
                className={`group rounded-lg border px-3 py-2 text-left transition ${
                  active
                    ? "border-indigo-500 bg-indigo-500/10 ring-1 ring-indigo-500"
                    : "border-slate-800 bg-slate-950/40 hover:border-slate-600 hover:bg-slate-900"
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span
                    className={`font-mono text-sm font-bold ${
                      active ? "text-indigo-200" : "text-slate-200"
                    }`}
                  >
                    {s.ticker}
                  </span>
                  <span className="text-[10px] uppercase tracking-wider text-slate-500">
                    {s.sector}
                  </span>
                </div>
                <div className="truncate text-xs text-slate-400">{s.name}</div>
              </button>
            );
          })}
          {filtered.length === 0 && (
            <div className="col-span-full rounded-md border border-dashed border-slate-800 px-3 py-4 text-center text-xs text-slate-500">
              No matches in the curated list. Use the custom ticker field below.
            </div>
          )}
        </div>
      </div>

      <details className="group rounded-md border border-slate-800 bg-slate-950/40">
        <summary className="cursor-pointer select-none px-3 py-2 text-xs uppercase tracking-wider text-slate-400 hover:text-slate-200">
          Use a custom ticker
        </summary>
        <div className="flex flex-wrap items-end gap-2 px-3 pb-3">
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && applyCustom()}
            placeholder="e.g. BRK-B"
            className="flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm uppercase placeholder-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <button
            onClick={applyCustom}
            disabled={!custom.trim()}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            Use ticker
          </button>
        </div>
      </details>
    </div>
  );
}
