import { useEffect, useMemo, useRef, useState } from "react";

import { api, type StockDirectory } from "../api/client";
import { browseAssets, filterAssets } from "../lib/stockCatalog";
import { StockBrowser } from "./StockBrowser";
export { POPULAR_STOCKS } from "../lib/stockCatalog";

interface Props {
  ticker: string;
  setTicker: (t: string) => void;
}

export function StockPicker({ ticker, setTicker }: Props) {
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState(false);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [directory, setDirectory] = useState<StockDirectory | null>(null);
  const [loading, setLoading] = useState(false);
  const [directoryError, setDirectoryError] = useState("");
  const [retry, setRetry] = useState(0);
  const pickerRef = useRef<HTMLDivElement>(null);

  const normalized = filter.trim().toUpperCase().replaceAll(".", "-");
  const assets = useMemo(() => browseAssets(directory?.assets ?? []), [directory]);
  const matching = useMemo(() => filterAssets(assets, filter), [assets, filter]);
  const filtered = matching.slice(0, 8);

  useEffect(() => {
    if ((!open && !browseOpen) || directory) return;
    let cancelled = false;
    setLoading(true);
    setDirectoryError("");
    api.stockDirectory().then((value) => {
      if (!cancelled) { setDirectory(value); setLoading(false); }
    }).catch((error: unknown) => {
      if (!cancelled) { setDirectoryError(error instanceof Error ? error.message : "Directory unavailable"); setLoading(false); }
    });
    return () => { cancelled = true; };
  }, [open, browseOpen, directory, retry]);

  function applyTicker(value = filter) {
    const t = value.trim().toUpperCase().replaceAll(".", "-");
    if (t) {
      setTicker(t);
      setFilter("");
      setOpen(false);
      setBrowseOpen(false);
    }
  }

  const exactMatch = assets.some((stock) => stock.ticker === normalized);
  const looksLikeTicker = /^[A-Z0-9.-]{1,10}$/.test(normalized);

  function openBoard() {
    setOpen(false);
    setBrowseOpen(true);
  }

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
      <div className="mb-2 flex items-center justify-between gap-3">
        <label htmlFor="asset-search" className="text-sm font-semibold text-slate-200">Stock or cryptocurrency</label>
        <button type="button" onClick={openBoard} aria-haspopup="dialog" className="flex shrink-0 items-center gap-1.5 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-xs font-semibold text-indigo-200 transition hover:border-indigo-400/60 hover:bg-indigo-500/20">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg>
          Browse all stocks
        </button>
      </div>
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
              if (e.key === "Enter") {
                e.preventDefault();
                if (normalized) applyTicker(filtered[0]?.ticker ?? filter);
              }
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
              {filtered.length === 0 && normalized && !looksLikeTicker && (
                <p className="px-3 py-4 text-sm text-slate-500">{loading ? "Searching the full directory…" : "No matching company. Try a ticker or browse the board."}</p>
              )}
            </div>
            <button type="button" onClick={openBoard} className="mt-2 flex min-h-11 w-full items-center justify-between rounded-lg border-t border-slate-700 px-3 py-2 text-left text-sm font-semibold text-indigo-300 hover:bg-slate-800">
              <span>{normalized && matching.length > 8 ? `See all ${matching.length.toLocaleString()} matches` : "Open the full stock board"}</span><span aria-hidden>↗</span>
            </button>
          </div>
        )}
      </div>
      {browseOpen && <StockBrowser ticker={ticker} directory={directory} loading={loading} error={directoryError} initialSearch={filter}
        onSelect={applyTicker} onClose={() => setBrowseOpen(false)} onRetry={() => setRetry((value) => value + 1)} />}
    </div>
  );
}
