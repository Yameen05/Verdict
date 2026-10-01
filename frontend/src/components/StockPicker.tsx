import { useEffect, useRef, useState } from "react";

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
  { ticker: "AVGO", name: "Broadcom", sector: "Semiconductors" },
  { ticker: "TSM", name: "TSMC", sector: "Semiconductors" },
  { ticker: "INTC", name: "Intel", sector: "Semiconductors" },
  { ticker: "SMCI", name: "Super Micro", sector: "Technology" },
  { ticker: "GOOGL", name: "Alphabet", sector: "Communication" },
  { ticker: "AMZN", name: "Amazon", sector: "Consumer" },
  { ticker: "META", name: "Meta Platforms", sector: "Communication" },
  { ticker: "TSLA", name: "Tesla", sector: "Auto" },
  { ticker: "ORCL", name: "Oracle", sector: "Technology" },
  { ticker: "CRM", name: "Salesforce", sector: "Technology" },
  { ticker: "ADBE", name: "Adobe", sector: "Technology" },
  { ticker: "UBER", name: "Uber", sector: "Technology" },
  { ticker: "ABNB", name: "Airbnb", sector: "Consumer" },
  { ticker: "SPOT", name: "Spotify", sector: "Communication" },
  { ticker: "PYPL", name: "PayPal", sector: "Financials" },
  { ticker: "HOOD", name: "Robinhood", sector: "Financials" },
  { ticker: "GME", name: "GameStop", sector: "Consumer" },
  { ticker: "RDDT", name: "Reddit", sector: "Communication" },
  { ticker: "LLY", name: "Eli Lilly", sector: "Healthcare" },
  { ticker: "BRK-B", name: "Berkshire Hathaway", sector: "Financials" },
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
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  const normalized = filter.trim().toUpperCase();
  const filtered = (filter
    ? POPULAR_STOCKS.filter(
        (s) =>
          s.ticker.toLowerCase().includes(filter.toLowerCase()) ||
          s.name.toLowerCase().includes(filter.toLowerCase()) ||
          s.sector.toLowerCase().includes(filter.toLowerCase()),
      )
    : POPULAR_STOCKS.slice(0, 8)
  ).slice(0, 8);

  function applyTicker(value = filter) {
    const t = value.trim().toUpperCase();
    if (t) {
      setTicker(t);
      setFilter("");
      setOpen(false);
    }
  }

  const exactMatch = POPULAR_STOCKS.some((stock) => stock.ticker === normalized);
  const looksLikeTicker = /^[A-Z0-9.^=-]{1,12}$/.test(normalized);

  useEffect(() => {
    function closeOnOutsideClick(event: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, []);

  return (
    <div ref={pickerRef}>
      <label htmlFor="asset-search" className="mb-2 block text-sm font-semibold text-slate-200">
        Stock or cryptocurrency
      </label>
      <div className="relative">
        <div className="flex min-h-12 items-center rounded-xl border border-slate-700 bg-slate-950/75 transition focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20">
          <svg
            width="19"
            height="19"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            aria-hidden
            className="ml-4 shrink-0 text-slate-500"
          >
            <circle cx="11" cy="11" r="6.5" />
            <path d="m16 16 4 4" />
          </svg>
          <input
            id="asset-search"
            value={filter}
            onFocus={() => setOpen(true)}
            onChange={(e) => {
              setFilter(e.target.value);
              setOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") applyTicker();
              if (e.key === "Escape") setOpen(false);
            }}
            placeholder="Search Apple, NVIDIA, Bitcoin, or enter a ticker"
            autoComplete="off"
            role="combobox"
            aria-expanded={open}
            aria-controls="asset-options"
            className="min-w-0 flex-1 bg-transparent px-3 py-3 text-base text-slate-100 placeholder-slate-500 focus:outline-none"
          />
          <span className="mr-3 hidden rounded-lg bg-indigo-500/12 px-2.5 py-1.5 font-mono text-sm font-semibold text-indigo-200 sm:inline">
            {ticker}
          </span>
        </div>

        {open && (
          <div
            id="asset-options"
            role="listbox"
            className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-20 overflow-hidden rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-2xl shadow-black/35"
          >
            <div className="max-h-72 overflow-y-auto">
              {filtered.map((stock) => (
                <button
                  key={stock.ticker}
                  type="button"
                  role="option"
                  aria-selected={stock.ticker === ticker}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyTicker(stock.ticker)}
                  className={`flex min-h-12 w-full items-center justify-between gap-4 rounded-lg px-3 text-left transition ${
                    stock.ticker === ticker
                      ? "bg-indigo-500/12 text-indigo-200"
                      : "text-slate-200 hover:bg-slate-800"
                  }`}
                >
                  <span className="min-w-0">
                    <span className="font-mono text-sm font-semibold">{stock.ticker}</span>
                    <span className="ml-2 text-sm text-slate-400">{stock.name}</span>
                  </span>
                  <span className="shrink-0 text-xs text-slate-500">{stock.sector}</span>
                </button>
              ))}

              {normalized && !exactMatch && looksLikeTicker && (
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => applyTicker()}
                  className="flex min-h-12 w-full items-center justify-between rounded-lg px-3 text-left text-slate-200 transition hover:bg-slate-800"
                >
                  <span className="text-sm">Use ticker</span>
                  <span className="font-mono text-sm font-semibold text-indigo-300">{normalized}</span>
                </button>
              )}

              {filtered.length === 0 && !normalized && (
                <p className="px-3 py-4 text-sm text-slate-500">Start typing to find an asset.</p>
              )}
            </div>
          </div>
        )}
      </div>

    </div>
  );
}
