import { useEffect, useMemo, useRef, useState } from "react";
import type { StockDirectory } from "../api/types";
import { browseAssets, filterAssets, type BrowseAsset } from "../lib/stockCatalog";

type Category = "stock" | "popular" | "etf" | "crypto";
const CATEGORIES: { value: Category; label: string }[] = [
  { value: "stock", label: "All stocks" },
  { value: "popular", label: "Popular" },
  { value: "etf", label: "ETFs" },
  { value: "crypto", label: "Crypto" },
];
const PAGE_SIZE = 72;

export function StockBrowser({ ticker, directory, loading, error, initialSearch, onSelect, onClose, onRetry }: {
  ticker: string;
  directory: StockDirectory | null;
  loading: boolean;
  error: string;
  initialSearch: string;
  onSelect: (ticker: string) => void;
  onClose: () => void;
  onRetry: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const results = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState(initialSearch);
  const [category, setCategory] = useState<Category>("stock");
  const [exchange, setExchange] = useState("All exchanges");
  const [page, setPage] = useState(0);
  const assets = useMemo(() => browseAssets(directory?.assets ?? []), [directory]);
  const exchanges = useMemo(() => [...new Set(assets.filter((a) => a.asset_class !== "crypto").map((a) => a.exchange))].sort(), [assets]);
  const matchesCategory = (asset: BrowseAsset, value: Category) => value === "popular"
    ? asset.popular && asset.asset_class === "stock" : asset.asset_class === value;
  const filtered = useMemo(() => filterAssets(assets.filter((asset) =>
    matchesCategory(asset, category) && (exchange === "All exchanges" || asset.exchange === exchange),
  ), query), [assets, category, exchange, query]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages - 1);
  const visible = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    search.current?.focus();
    return () => element?.close();
  }, []);
  useEffect(() => { setPage(0); }, [category, exchange, query]);
  useEffect(() => { results.current?.scrollTo({ top: 0 }); }, [currentPage, category, exchange, query]);

  return (
    <dialog ref={dialog} aria-labelledby="stock-browser-title" aria-describedby="stock-browser-description"
      onCancel={onClose}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
      className="h-[min(92dvh,60rem)] max-h-[92dvh] w-[min(96vw,80rem)] max-w-none flex-col overflow-hidden rounded-3xl border border-slate-700 bg-slate-950 p-0 text-slate-200 shadow-2xl backdrop:bg-slate-950/80 open:flex"
    >
      <header className="border-b border-slate-800 bg-gradient-to-br from-indigo-950/60 via-slate-950 to-slate-950 px-5 py-5 sm:px-7">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-300">Find your next ticker</p>
            <h2 id="stock-browser-title" className="mt-1 font-display text-2xl text-white">Browse the market</h2>
            <p id="stock-browser-description" className="mt-1 text-sm text-slate-400">Pick a company to load its chart. Run an analysis whenever you’re ready.</p>
          </div>
          <button type="button" onClick={onClose} className="shrink-0 rounded-full border border-slate-700 px-4 py-2 text-sm transition hover:border-slate-500 hover:bg-slate-800">Close board</button>
        </div>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <input ref={search} autoFocus type="search" aria-label="Search the stock board" value={query} onChange={(event) => setQuery(event.target.value)}
            placeholder="Search a company or ticker…"
            className="min-h-12 min-w-0 flex-1 rounded-xl border border-slate-700 bg-slate-900 px-4 text-base text-white placeholder-slate-500 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20" />
          <select aria-label="Filter by exchange" value={exchange} disabled={category === "crypto"}
            onChange={(event) => setExchange(event.target.value)}
            className="min-h-12 rounded-xl border border-slate-700 bg-slate-900 px-3 text-sm focus:border-indigo-400 focus:outline-none disabled:opacity-40">
            <option>All exchanges</option>
            {exchanges.map((value) => <option key={value}>{value}</option>)}
          </select>
        </div>
        <div role="group" aria-label="Asset category" className="mt-4 flex flex-wrap gap-2">
          {CATEGORIES.map(({ value, label }) => <button key={value} type="button" aria-pressed={category === value}
            onClick={() => { setCategory(value); setExchange("All exchanges"); }}
            className={`rounded-full border px-3.5 py-2 text-sm transition ${category === value ? "border-indigo-400/50 bg-indigo-500/20 text-indigo-100" : "border-slate-800 text-slate-400 hover:border-slate-600 hover:text-white"}`}>
            {label} <span className="ml-1.5 text-xs opacity-70">{assets.filter((asset) => matchesCategory(asset, value)).length.toLocaleString()}</span>
          </button>)}
        </div>
      </header>
      <div ref={results} className="min-h-0 flex-1 overflow-y-auto px-5 py-4 sm:px-7">
        {loading && <p role="status" className="mb-4 rounded-xl bg-indigo-500/10 px-4 py-3 text-sm text-indigo-200">Loading the full directory… Popular names are ready to choose below.</p>}
        {error && <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <span>The full directory couldn’t load. You can still choose a popular asset or enter a ticker in search.</span>
          <button type="button" onClick={onRetry} className="rounded-full border border-amber-400/40 px-3 py-1.5">Retry directory</button>
        </div>}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400" aria-live="polite">
          <span>{filtered.length.toLocaleString()} {category === "popular" ? "popular stocks" : category === "crypto" ? "cryptocurrencies" : category === "etf" ? "ETFs" : "stocks"}{query.trim() ? ` matching “${query.trim()}”` : ""}</span>
          <span>Popular names first · then A–Z</span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visible.map((asset) => <button type="button" key={asset.ticker} aria-label={`Choose ${asset.name} (${asset.ticker})`} aria-pressed={asset.ticker === ticker}
            onClick={() => onSelect(asset.ticker)}
            className={`group flex min-h-36 flex-col rounded-2xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${asset.ticker === ticker ? "border-indigo-400/60 bg-indigo-500/15" : "border-slate-800 bg-slate-900/60 hover:border-indigo-500/50 hover:bg-slate-900"}`}>
            <span className="flex w-full items-center justify-between gap-2">
              <span className="font-mono text-lg font-bold text-slate-100 group-hover:text-indigo-200">{asset.ticker}</span>
              {asset.ticker === ticker ? <span className="text-xs text-indigo-300">Selected ✓</span> : asset.popular ? <span className="rounded-full bg-indigo-500/10 px-2 py-1 text-[10px] text-indigo-300">Popular</span> : null}
            </span>
            <span className="mt-2 line-clamp-2 text-sm leading-5 text-slate-300" title={asset.name}>{asset.name}</span>
            <span className="mt-auto flex w-full items-end justify-between gap-2 pt-3 text-[11px] text-slate-500"><span>{asset.sector}</span><span>{asset.exchange}</span></span>
          </button>)}
        </div>
        {!filtered.length && <div className="py-16 text-center"><p className="text-slate-200">No matches in this view.</p><p className="mt-2 text-sm text-slate-400">Try another category, company name, or exchange.</p>
          <button type="button" onClick={() => { setQuery(""); setExchange("All exchanges"); }} className="mt-4 rounded-full border border-slate-700 px-4 py-2 text-sm">Clear filters</button>
        </div>}
      </div>
      <footer className="border-t border-slate-800 bg-slate-950 px-5 py-3 sm:px-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-400">{filtered.length ? `${currentPage * PAGE_SIZE + 1}–${Math.min((currentPage + 1) * PAGE_SIZE, filtered.length)} of ${filtered.length.toLocaleString()}` : "0 results"} · Page {currentPage + 1} of {pages}</p>
          <div className="flex gap-2">
            <button type="button" aria-label="Previous page of stocks" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)} className="rounded-full border border-slate-700 px-4 py-2 text-xs disabled:opacity-30">Previous</button>
            <button type="button" aria-label="Next page of stocks" disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)} className="rounded-full border border-slate-700 px-4 py-2 text-xs disabled:opacity-30">Next</button>
          </div>
        </div>
        <p className="mt-2 text-[11px] leading-5 text-slate-500">US listings from Nasdaq Trader{directory ? ` · Loaded ${new Date(directory.fetched_at).toLocaleDateString()}` : ""}. Crypto is a curated list. Other supported tickers can still be entered manually. Data coverage varies by asset. Browsing uses no AI runs.</p>
      </footer>
    </dialog>
  );
}
