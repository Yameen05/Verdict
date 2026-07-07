import { useEffect, useState } from "react";

const STORAGE_KEY = "verdict.watchlist";

function load(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((t): t is string => typeof t === "string") : [];
  } catch {
    return [];
  }
}

interface Props {
  ticker: string;
  onSelect: (ticker: string) => void;
}

export function WatchlistBar({ ticker, onSelect }: Props) {
  const [list, setList] = useState<string[]>(load);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  }, [list]);

  const watching = list.includes(ticker);

  function toggle() {
    setList((l) => (watching ? l.filter((t) => t !== ticker) : [...l, ticker].slice(0, 12)));
  }

  if (list.length === 0 && !ticker) return null;

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Watchlist
      </span>
      {list.map((t) => (
        <span
          key={t}
          className={`inline-flex items-center overflow-hidden rounded-full border text-xs font-mono ${
            t === ticker
              ? "border-indigo-500 bg-indigo-500/15 text-indigo-200"
              : "border-slate-700 bg-slate-900 text-slate-300"
          }`}
        >
          <button onClick={() => onSelect(t)} className="px-2.5 py-1 hover:text-white">
            {t}
          </button>
          <button
            onClick={() => setList((l) => l.filter((x) => x !== t))}
            className="pr-2 text-slate-500 hover:text-rose-400"
            title={`Remove ${t} from watchlist`}
            aria-label={`Remove ${t} from watchlist`}
          >
            ×
          </button>
        </span>
      ))}
      <button
        onClick={toggle}
        className={`rounded-full border border-dashed px-2.5 py-1 text-xs transition ${
          watching
            ? "border-slate-700 text-slate-500 hover:text-slate-300"
            : "border-indigo-500/50 text-indigo-300 hover:bg-indigo-500/10"
        }`}
      >
        {watching ? `★ ${ticker} watched` : `☆ Watch ${ticker}`}
      </button>
    </div>
  );
}
