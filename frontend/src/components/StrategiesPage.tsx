import { useEffect, useMemo, useRef, useState } from "react";
import { api, type ListedAsset } from "../api/client";
import {
  practiceApi,
  type Account,
  type Quote,
  type Scan,
  type Strategy,
  type StrategyList,
  type StrategyRules,
  type Template,
} from "../api/practice";
import {
  friendlyPracticeError,
  ideaFor,
  starterIdeas,
} from "../lib/practiceGuide";
import { browseAssets } from "../lib/stockCatalog";
import { PracticeJournal } from "./practice/PracticeJournal";
import { PracticePlan } from "./practice/PracticePlan";
import {
  asOf,
  button,
  Checks,
  Field,
  input,
  money,
  panel,
  PriceNote,
  primary,
} from "./practice/PracticeShared";

const defaultRules = (template: Template): StrategyRules => ({
  name: ideaFor(template).name,
  template,
  lookback: 20,
  volume_multiple: 1.5,
  tolerance_pct: 2,
  rsi_threshold: 30,
});
const steps = [
  "Choose an idea",
  "Find stocks",
  "Read one result",
  "Try pretend money",
  "See what happened",
];

export function StrategiesPage({
  onResearch,
}: {
  onResearch: (ticker: string) => void;
}) {
  const [view, setView] = useState<"find" | "practice">("find");
  const [catalog, setCatalog] = useState<StrategyList | null>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [directory, setDirectory] = useState<ListedAsset[]>([]);
  const [chosen, setChosen] = useState(false);
  const [rules, setRules] = useState<StrategyRules>(defaultRules("breakout"));
  const [editing, setEditing] = useState<number>();
  const [universe, setUniverse] = useState<Scan["universe"]>("liquid");
  const [scan, setScan] = useState<Scan | null>(null);
  const [onlyMatches, setOnlyMatches] = useState(true);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const setupRef = useRef<HTMLElement>(null);
  const resultsRef = useRef<HTMLElement>(null);
  const assets = useMemo(
    () =>
      new Map(browseAssets(directory).map((asset) => [asset.ticker, asset])),
    [directory],
  );
  const nameFor = (ticker: string) => assets.get(ticker)?.name ?? ticker;
  const ideas = catalog?.templates ?? starterIdeas;
  const idea =
    ideas.find((i) => i.template === rules.template) ?? ideaFor(rules.template);
  const stage = view === "practice" ? 5 : quote ? 4 : scan ? 3 : chosen ? 2 : 1;

  useEffect(() => {
    let cancelled = false;
    practiceApi
      .strategies()
      .then((data) => {
        if (!cancelled) setCatalog(data);
      })
      .catch((e) => {
        if (!cancelled) setError(friendlyPracticeError(e));
      });
    practiceApi
      .account()
      .then((data) => {
        if (!cancelled) setAccount(data);
      })
      .catch((e) => {
        if (!cancelled) setError(friendlyPracticeError(e));
      });
    api
      .stockDirectory()
      .then((data) => {
        if (!cancelled) setDirectory(data.assets);
      })
      .catch(() => {
        /* Known company names remain available if the directory is down. */
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    if (chosen && !scan)
      setupRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [chosen, editing, Boolean(scan)]);
  useEffect(() => {
    if (scan)
      resultsRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
  }, [scan?.scanned_at]);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(friendlyPracticeError(e));
    } finally {
      setBusy(false);
    }
  }
  function choose(template: Template) {
    setRules(defaultRules(template));
    setEditing(undefined);
    setChosen(true);
    setScan(null);
    setQuote(null);
    setError("");
    setNotice("");
    setView("find");
  }
  function useSaved(saved: Strategy) {
    const { id, ...settings } = saved;
    setRules(settings);
    setEditing(id);
    setChosen(true);
    setScan(null);
    setQuote(null);
    setError("");
    setNotice("");
    setView("find");
  }
  function startOver() {
    setChosen(false);
    setEditing(undefined);
    setScan(null);
    setQuote(null);
    setView("find");
    setError("");
    setNotice("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function setRule(key: keyof StrategyRules, value: string | number) {
    setRules((old) => ({ ...old, [key]: value }));
    setScan(null);
    setQuote(null);
  }
  async function saveRules(find: boolean) {
    const saved = await practiceApi.save(rules, editing);
    setEditing(saved.id);
    setCatalog(await practiceApi.strategies());
    setScan(null);
    setQuote(null);
    if (find) {
      setScan(await practiceApi.scan(saved.id, universe));
      setOnlyMatches(true);
    } else {
      setNotice(
        "Your search is saved. Choose “Find stocks” when you want to use it.",
      );
    }
  }
  async function preview(strategyId: number, ticker: string) {
    const [next, cash] = await Promise.all([
      practiceApi.quote(strategyId, ticker),
      practiceApi.account(),
    ]);
    setAccount(cash);
    setQuote(next);
  }
  const matches = scan?.results.filter((r) => r.matched).length ?? 0;
  const results = scan?.results.filter((r) => !onlyMatches || r.matched) ?? [];

  return (
    <div className="space-y-7">
      <header className="max-w-3xl">
        <p className="text-sm font-semibold text-indigo-300">
          Strategies & practice
        </p>
        <h1 className="mt-1 font-display text-3xl font-medium tracking-tight text-slate-50 sm:text-4xl">
          Try stocks without using real money
        </h1>
        <p className="mt-3 leading-7 text-slate-300">
          A stock is a small piece of a company. A share is one piece you can
          buy. Here, you can find an idea, try buying shares with pretend money,
          and see what happens.
        </p>
      </header>
      <ol
        className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-5"
        aria-label="How to get started"
      >
        {steps.map((step, i) => (
          <li
            key={step}
            aria-current={stage === i + 1 ? "step" : undefined}
            className={`${i === 4 ? "col-span-2 sm:col-span-1" : ""} flex items-center gap-2 rounded-xl border px-3 py-3 ${stage === i + 1 ? "border-indigo-500 bg-indigo-500/10 text-indigo-200" : "border-slate-800 text-slate-400"}`}
          >
            <span className="font-mono">{i + 1}</span>
            {step}
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-2" aria-label="Choose a view">
        <button
          className={view === "find" ? primary : button}
          aria-pressed={view === "find"}
          onClick={() => setView("find")}
        >
          Find stocks
        </button>
        <button
          className={view === "practice" ? primary : button}
          aria-pressed={view === "practice"}
          onClick={() => setView("practice")}
        >
          My practice & notes
        </button>
      </div>
      {error && (
        <div
          role="alert"
          className="rounded-xl border border-rose-800 bg-rose-950/30 p-4 text-sm text-rose-200"
        >
          <p>{error}</p>
          {!catalog && (
            <button
              className={`${button} mt-3`}
              disabled={busy}
              onClick={() =>
                void run(async () => setCatalog(await practiceApi.strategies()))
              }
            >
              Try loading again
            </button>
          )}
        </div>
      )}
      {notice && (
        <p role="status" className="text-sm text-emerald-300">
          {notice}
        </p>
      )}

      <div hidden={view !== "find"} className="space-y-7">
        {!chosen && (
          <section className="space-y-4">
            <div className="max-w-3xl">
              <p className="text-sm text-indigo-300">Step 1 · Choose an idea</p>
              <h2 className="mt-1 font-display text-2xl text-slate-100">
                Start with one of these three ideas
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                These are starting ideas, not saved work or promises of profit.
                A “strategy” just means an idea with rules you can check again.
                You can change the rules later.
              </p>
            </div>
            <div className="grid gap-4 xl:grid-cols-3">
              {ideas.map((starter, i) => (
                <article
                  className={`${panel} flex flex-col items-start gap-4`}
                  key={starter.template}
                >
                  <p className="text-xs text-slate-500">
                    Starting idea {i + 1}
                  </p>
                  <h3 className="font-display text-xl text-slate-100">
                    {starter.name}
                  </h3>
                  <p className="text-sm leading-6 text-slate-300">
                    {starter.lesson}
                  </p>
                  <p className="text-sm leading-6 text-slate-400">
                    {starter.why}
                  </p>
                  <button
                    className={`${primary} mt-auto`}
                    disabled={busy || !catalog}
                    onClick={() => choose(starter.template)}
                  >
                    Use this idea
                  </button>
                </article>
              ))}
            </div>
            {!catalog && !error && (
              <p role="status" className="text-sm text-slate-400">
                Loading your saved searches…
              </p>
            )}
          </section>
        )}
        {chosen && !scan && !quote && (
          <section
            ref={setupRef}
            className={`${panel} space-y-5 scroll-mt-24 lg:scroll-mt-6`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="max-w-3xl">
                <p className="text-sm text-indigo-300">Step 2 · Find stocks</p>
                <h2 className="mt-1 font-display text-2xl text-slate-100">
                  {idea.name}
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  {idea.lesson}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  We will check recent prices for stocks that fit this idea.
                  Finding a match does not mean you should buy it.
                </p>
              </div>
              <button className={button} disabled={busy} onClick={startOver}>
                Choose a different idea
              </button>
            </div>
            <form
              className="space-y-5"
              onSubmit={(e) => {
                e.preventDefault();
                void run(() => saveRules(true));
              }}
            >
              <Field label="Which stocks should I check?">
                <select
                  className={`${input} sm:max-w-lg`}
                  disabled={busy}
                  value={universe}
                  onChange={(e) => {
                    setUniverse(e.target.value as Scan["universe"]);
                    setScan(null);
                    setQuote(null);
                  }}
                >
                  <option value="liquid">
                    Starter list — 12 companies and funds
                  </option>
                  <option value="watchlist">
                    My watchlist — names I saved in Research
                  </option>
                </select>
              </Field>
              <p className="text-xs leading-6 text-slate-400">
                {universe === "liquid"
                  ? "The starter list is a small set we can check quickly. A fund puts several investments into one share."
                  : "Checks up to 24 supported US stocks or funds from your Research watchlist. Coins are not included here."}
              </p>
              <details className="space-y-4">
                <summary className="cursor-pointer text-sm text-indigo-300">
                  Change this idea (optional)
                </summary>
                <p className="text-sm leading-6 text-slate-400">
                  The starter settings work as a first try. You can leave these
                  alone. Changes affect this saved search; old practice plans
                  stay as they were.
                </p>
                <Field
                  label="Starting idea for this search"
                  hint="You can switch to another idea and keep this saved search."
                >
                  <select
                    className={input}
                    value={rules.template}
                    disabled={busy}
                    onChange={(e) =>
                      setRule("template", e.target.value as Template)
                    }
                  >
                    {ideas.map((starter) => (
                      <option value={starter.template} key={starter.template}>
                        {starter.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Name for my saved search">
                  <input
                    required
                    maxLength={80}
                    className={input}
                    value={rules.name}
                    onChange={(e) => setRule("name", e.target.value)}
                  />
                </Field>
                {rules.template !== "rsi_recovery" && (
                  <Field
                    label="How many past trading days should I compare?"
                    hint="Trading days are days when the stock market is open. The starter uses 20."
                  >
                    <input
                      required
                      type="number"
                      min={10}
                      max={60}
                      step={1}
                      className={input}
                      value={rules.lookback}
                      onChange={(e) =>
                        setRule("lookback", Number(e.target.value))
                      }
                    />
                  </Field>
                )}
                {rules.template === "breakout" && (
                  <Field
                    label="How much extra buying and selling should I look for?"
                    hint="1.5 means at least one and a half times the usual number of shares traded. This is often called volume."
                  >
                    <input
                      required
                      type="number"
                      min={1}
                      max={5}
                      step={0.1}
                      className={input}
                      value={rules.volume_multiple}
                      onChange={(e) =>
                        setRule("volume_multiple", Number(e.target.value))
                      }
                    />
                  </Field>
                )}
                {rules.template === "pullback" && (
                  <Field
                    label="How close to its usual price? (%)"
                    hint="The starter looks within 2% of the average over your chosen days. An average that changes each day is called a moving average."
                  >
                    <input
                      required
                      type="number"
                      min={0.1}
                      max={10}
                      step={0.1}
                      className={input}
                      value={rules.tolerance_pct}
                      onChange={(e) =>
                        setRule("tolerance_pct", Number(e.target.value))
                      }
                    />
                  </Field>
                )}
                {rules.template === "rsi_recovery" && (
                  <Field
                    label="Where should the recovery line be?"
                    hint="The starter uses 30 on a 0–100 price-change measure called RSI. It checks gains and losses over 14 trading days."
                  >
                    <input
                      required
                      type="number"
                      min={10}
                      max={50}
                      step={1}
                      className={input}
                      value={rules.rsi_threshold}
                      onChange={(e) =>
                        setRule("rsi_threshold", Number(e.target.value))
                      }
                    />
                  </Field>
                )}
                <button
                  type="button"
                  className={button}
                  disabled={busy}
                  onClick={() => void run(() => saveRules(false))}
                >
                  Save without searching
                </button>
              </details>
              <div className="flex flex-wrap items-center gap-3">
                <button className={primary} disabled={busy || !catalog}>
                  {busy
                    ? "Checking…"
                    : editing
                      ? "Find stocks with this idea"
                      : "Save this idea & find stocks"}
                </button>
                <span className="text-xs text-slate-400">
                  Free rule search · no AI runs
                </span>
              </div>
              <PriceNote />
              {universe === "liquid" && (
                <details>
                  <summary className="cursor-pointer text-xs text-slate-500">
                    Which names are on the starter list?
                  </summary>
                  <p className="mt-2 text-xs leading-6 text-slate-400">
                    {catalog?.liquid_universe
                      .map((t) => `${nameFor(t)} (${t})`)
                      .join(" · ")}
                  </p>
                </details>
              )}
            </form>
          </section>
        )}
        {chosen && (scan || quote) && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 px-4 py-3">
            <p className="text-sm text-slate-400">
              Your search: <span className="text-slate-200">{rules.name}</span>
            </p>
            <button
              className={button}
              disabled={busy}
              onClick={() => {
                setScan(null);
                setQuote(null);
              }}
            >
              Change this search
            </button>
          </div>
        )}
        {quote && (
          <PracticePlan
            key={`${quote.ticker}:${quote.strategy.id}`}
            quote={quote}
            account={account}
            name={nameFor(quote.ticker)}
            busy={busy}
            onCancel={() => {
              setQuote(null);
              resultsRef.current?.scrollIntoView({ behavior: "smooth" });
            }}
            onRefresh={() =>
              void run(() => preview(quote.strategy.id, quote.ticker))
            }
            onBuy={(plan) =>
              void run(async () => {
                await practiceApi.place(plan);
                setQuote(null);
                setView("practice");
                setAccount(await practiceApi.account());
                setNotice(
                  "You bought practice shares with pretend money. You can see them below. When you want to finish, choose “Sell my practice shares”.",
                );
                window.scrollTo({ top: 0, behavior: "smooth" });
              })
            }
          />
        )}
        {scan && !quote && (
          <section
            ref={resultsRef}
            className="space-y-4 scroll-mt-24 lg:scroll-mt-6"
          >
            <header className="max-w-3xl">
              <p className="text-sm text-indigo-300">
                Step 3 · Understand one result
              </p>
              <h2 className="mt-1 font-display text-2xl text-slate-100">
                {matches > 0
                  ? `${matches} ${matches === 1 ? "name fits" : "names fit"} your idea`
                  : "No full matches this time"}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                {scan.strategy.name} · Checked {scan.results.length} · Could not
                check {scan.skipped.length}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                Read why one result appeared, then try it with pretend money if
                you want. Letter codes like AAPL are short names used on stock
                lists. Fitting an idea does not mean the price will go up.
              </p>
            </header>
            {results.length === 0 && (
              <div className={`${panel} space-y-4`}>
                <p className="text-sm leading-6 text-slate-300">
                  {scan.tickers.length === 0
                    ? "There are no supported stocks or funds on your watchlist yet. Add some in Research, or check the starter list."
                    : scan.results.length === 0
                      ? "We could not get enough recent prices to check these names. We will not fill in missing prices."
                      : "None of these names fits every condition right now. That is normal; you do not need to buy anything. You can look at what did not fit or choose another idea."}
                </p>
                <div className="flex flex-wrap gap-2">
                  {scan.results.length > 0 && (
                    <button
                      className={button}
                      disabled={busy}
                      onClick={() => setOnlyMatches(false)}
                    >
                      See what did not fit
                    </button>
                  )}
                  <button
                    className={button}
                    disabled={busy}
                    onClick={startOver}
                  >
                    Try another idea
                  </button>
                  {scan.tickers.length === 0 && (
                    <button
                      className={primary}
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          setUniverse("liquid");
                          setScan(
                            await practiceApi.scan(scan.strategy.id, "liquid"),
                          );
                        })
                      }
                    >
                      Check the starter list
                    </button>
                  )}
                </div>
              </div>
            )}
            {scan.results.length > 0 && (
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={!onlyMatches}
                  onChange={(e) => setOnlyMatches(!e.target.checked)}
                />
                Also show names that did not fully fit
              </label>
            )}
            <div className="grid gap-4 xl:grid-cols-2">
              {results.map((result) => (
                <article className={`${panel} space-y-4`} key={result.ticker}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-display text-xl text-slate-100">
                        {nameFor(result.ticker)}
                      </h3>
                      <p className="mt-1 text-sm text-slate-400">
                        {result.ticker}
                        {assets.get(result.ticker)?.asset_class === "etf"
                          ? " · Fund"
                          : ""}{" "}
                        · {money(result.close)} for one share
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        Price from {asOf(result.as_of)} · not live
                      </p>
                    </div>
                    <span
                      className={`rounded-full px-3 py-1 text-xs ${result.matched ? "bg-emerald-900/30 text-emerald-300" : "bg-amber-900/30 text-amber-300"}`}
                    >
                      {result.matched ? "Fits this idea" : "Does not fully fit"}
                    </span>
                  </div>
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-slate-200">
                      {result.matched
                        ? "Why this showed up"
                        : "What fits and what does not"}
                    </h4>
                    <Checks evaluation={result} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className={primary}
                      disabled={busy}
                      onClick={() =>
                        void run(() => preview(scan.strategy.id, result.ticker))
                      }
                    >
                      Try with pretend money
                    </button>
                    <button
                      className={button}
                      disabled={busy}
                      onClick={() => onResearch(result.ticker)}
                    >
                      Read more in Research
                    </button>
                  </div>
                  <p className="text-xs leading-5 text-slate-500">
                    Opening Research is free. AI research starts only if you
                    choose Analyze there.
                  </p>
                </article>
              ))}
            </div>
            {scan.skipped.length > 0 && (
              <details className={panel}>
                <summary className="cursor-pointer text-sm text-slate-300">
                  Names we could not check ({scan.skipped.length})
                </summary>
                <ul className="mt-3 space-y-2 text-sm text-slate-400">
                  {scan.skipped.map((s) => (
                    <li key={s.ticker}>
                      {nameFor(s.ticker)} ({s.ticker}): {s.reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        )}
        {!scan && !quote && (
          <section className={`${panel} space-y-3`}>
            <h2 className="font-display text-xl text-slate-100">
              Your saved searches
            </h2>
            <p className="text-sm leading-6 text-slate-400">
              These are searches you have saved yourself. Use one again or
              change its settings.
            </p>
            {catalog?.strategies.length === 0 ? (
              <p className="text-sm text-slate-300">
                Nothing saved yet. Choose a starting idea, then use “Save this
                idea & find stocks”.
              </p>
            ) : (
              <ul className="divide-y divide-slate-800">
                {catalog?.strategies.map((saved) => (
                  <li
                    className="flex flex-wrap items-center justify-between gap-3 py-3"
                    key={saved.id}
                  >
                    <div>
                      <p className="text-sm text-slate-200">{saved.name}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        Based on: {ideaFor(saved.template).name}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        className={button}
                        disabled={busy}
                        onClick={() => useSaved(saved)}
                      >
                        Use saved search
                      </button>
                      <button
                        className={button}
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            await practiceApi.remove(saved.id);
                            setCatalog(await practiceApi.strategies());
                            if (editing === saved.id) startOver();
                            setNotice(
                              "Saved search deleted. Your past practice plans and notes are still here.",
                            );
                          })
                        }
                      >
                        Delete search
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
      {view === "practice" && (
        <PracticeJournal
          account={account}
          busy={busy}
          nameFor={nameFor}
          onRefresh={() =>
            void run(async () => setAccount(await practiceApi.account()))
          }
          onStart={startOver}
          onResearch={onResearch}
          onSave={(trade, notes) =>
            void run(async () => {
              await practiceApi.notes(trade.id, notes);
              setAccount(await practiceApi.account());
              setNotice("Your notes are saved.");
            })
          }
          onSell={(trade) =>
            void run(async () => {
              const sold = await practiceApi.close(trade.id);
              setAccount(await practiceApi.account());
              setNotice(
                `You sold your practice shares for ${money((sold.exit_price ?? 0) * sold.quantity)} pretend money. Your gain or loss is saved below.`,
              );
            })
          }
        />
      )}
    </div>
  );
}
