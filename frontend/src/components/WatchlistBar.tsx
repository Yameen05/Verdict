import { useEffect, useState } from "react";
import { userStateApi } from "../api/client";

interface Props {
  ticker: string;
  onSelect: (ticker: string) => void;
}

export function WatchlistBar({ ticker, onSelect }: Props) {
  const [list, setList] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    userStateApi
      .watchlist()
      .then((res) => {
        if (!cancelled) setList(res.tickers);
      })
      .catch(() => {
        if (!cancelled) setError("Watchlist unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const watching = list.includes(ticker);

  function apply(promise: Promise<{ tickers: string[] }>) {
    promise
      .then((res) => {
        setList(res.tickers);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Watchlist update failed"),
      );
  }

  function toggle() {
    apply(
      watching ? userStateApi.removeWatchlist(ticker) : userStateApi.addWatchlist(ticker),
    );
  }

  if (list.length === 0 && !ticker) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-800/80 bg-slate-900/45 px-4 py-3">
      <span className="mr-1 text-sm font-semibold text-slate-300">
        Your watchlist
      </span>
      {list.map((t) => (
        <span
          key={t}
          className={`inline-flex min-h-9 items-center overflow-hidden rounded-lg border text-xs font-mono ${
            t === ticker
              ? "border-indigo-500 bg-indigo-500/15 text-indigo-200"
              : "border-slate-700 bg-slate-900 text-slate-300"
          }`}
        >
          <button onClick={() => onSelect(t)} className="self-stretch px-2.5 hover:text-white">
            {t}
          </button>
          <button
            onClick={() => apply(userStateApi.removeWatchlist(t))}
            className="self-stretch px-2 text-slate-500 hover:bg-rose-500/10 hover:text-rose-400"
            title={`Remove ${t} from watchlist`}
            aria-label={`Remove ${t} from watchlist`}
          >
            ×
          </button>
        </span>
      ))}
      <button
        onClick={toggle}
        className={`min-h-9 rounded-lg border border-dashed px-3 text-xs font-medium transition ${
          watching
            ? "border-slate-700 text-slate-500 hover:text-slate-300"
            : "border-indigo-500/50 text-indigo-300 hover:bg-indigo-500/10"
        }`}
      >
        {watching ? `★ ${ticker} watched` : `☆ Watch ${ticker}`}
      </button>
      {error && <span className="text-xs text-rose-400">{error}</span>}
    </div>
  );
}
