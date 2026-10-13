import { useEffect, useRef, useState } from "react";
import type { Account, Quote } from "../../api/practice";
import { ideaFor } from "../../lib/practiceGuide";
import { practiceSize } from "../../lib/practiceMath";
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
} from "./PracticeShared";

export interface BuyPlan {
  quote_id: string;
  quantity: number;
  stop: number;
  target: number;
  thesis: string;
}
export function PracticePlan({
  quote,
  account,
  name,
  busy,
  onBuy,
  onRefresh,
  onCancel,
}: {
  quote: Quote;
  account: Account | null;
  name: string;
  busy: boolean;
  onBuy: (plan: BuyPlan) => void;
  onRefresh: () => void;
  onCancel: () => void;
}) {
  const [quantity, setQuantity] = useState(1);
  const [stop, setStop] = useState(
    Number((quote.entry_price * 0.97).toFixed(2)),
  );
  const [target, setTarget] = useState(
    Number((quote.entry_price * 1.06).toFixed(2)),
  );
  const [thesis, setThesis] = useState("");
  const [riskPct, setRiskPct] = useState(1);
  const [clock, setClock] = useState(Date.now());
  const ref = useRef<HTMLFormElement>(null);
  useEffect(() => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    ref.current?.focus({ preventScroll: true });
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const cost = quantity * quote.entry_price;
  const expired = new Date(quote.expires_at).getTime() <= clock;
  const valid =
    account != null &&
    Number.isInteger(quantity) &&
    quantity >= 1 &&
    quantity <= 1_000_000 &&
    Number.isFinite(stop) &&
    stop > 0 &&
    stop < quote.entry_price &&
    Number.isFinite(target) &&
    target > quote.entry_price &&
    target <= 100_000_000 &&
    thesis.trim().length > 0 &&
    quantity * Math.round(quote.entry_price * 100) <=
      Math.round(account.cash * 100);
  const nextHint =
    !Number.isInteger(quantity) || quantity < 1 || quantity > 1_000_000
      ? "Choose a whole number of shares, from 1 to 1,000,000."
      : !Number.isFinite(stop) || stop <= 0 || stop >= quote.entry_price
        ? "Choose a lower sell price below the buying price."
        : !Number.isFinite(target) ||
            target <= quote.entry_price ||
            target > 100_000_000
          ? "Choose a higher sell price above the buying price."
          : account && cost > account.cash
            ? "That costs more than your pretend balance. Try fewer shares."
            : !thesis.trim()
              ? "Add a quick note above, or choose “Use a starter note”, to finish your plan."
              : !account
                ? "Your pretend balance has not loaded. Choose “Update price preview” to try again."
                : "";
  const starterNote = `I'm trying “${ideaFor(quote.strategy.template).name}” with pretend money. I'll check the price and my sell plan after the next trading day.`;
  return (
    <form
      ref={ref}
      tabIndex={-1}
      aria-label="Practice buying shares"
      className={`${panel} space-y-5 border-indigo-700 scroll-mt-24 lg:scroll-mt-6`}
      onSubmit={(e) => {
        e.preventDefault();
        onBuy({ quote_id: quote.id, quantity, stop, target, thesis });
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-indigo-300">
            Step 4 · Try it with pretend money
          </p>
          <h2 className="mt-1 font-display text-2xl text-slate-100">
            Try buying {name}
          </h2>
          <p className="mt-2 text-sm text-slate-400">
            {quote.ticker} · {money(quote.entry_price)} for one share · Recorded{" "}
            {asOf(quote.evaluation.as_of)}
          </p>
        </div>
        <button
          type="button"
          className={button}
          disabled={busy}
          onClick={onCancel}
        >
          Back to results
        </button>
      </div>
      <PriceNote />
      {!quote.evaluation.matched && (
        <p className="rounded-xl bg-amber-950/30 p-3 text-sm text-amber-200">
          This stock does not fit every condition in your idea. You can still
          try it, and your notes will keep that fact.
        </p>
      )}
      <Field
        label="How many shares would you like to try?"
        hint="A share is one piece you can buy. Starting with one lets you see how this works."
      >
        <input
          required
          type="number"
          min={1}
          max={1_000_000}
          step={1}
          className={`${input} sm:max-w-xs`}
          value={quantity}
          onChange={(e) => setQuantity(Number(e.target.value))}
        />
      </Field>
      <div className="rounded-xl border border-slate-700 bg-slate-950/50 p-4 text-sm leading-7 text-slate-300">
        <p>
          {quantity} {quantity === 1 ? "share" : "shares"} ×{" "}
          {money(quote.entry_price)} ={" "}
          <strong className="text-slate-100">{money(cost)}</strong> pretend
          money.
        </p>
        <p>
          This comes out of your {money(account?.cash)} pretend balance. You
          would have{" "}
          <strong>{money(account ? account.cash - cost : null)}</strong> left to
          spend.
        </p>
      </div>
      <div className="space-y-3">
        <h3 className="text-lg text-slate-100">
          Choose when you would think about selling
        </h3>
        <p className="text-sm leading-6 text-slate-400">
          These prices are reminders for your plan. The app will not sell for
          you. You can change the starter values below.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="If the price falls to… ($)"
            hint="A lower price where you would consider selling to limit a loss."
          >
            <input
              required
              type="number"
              min={0.01}
              max={quote.entry_price - 0.01}
              step={0.01}
              value={stop}
              className={input}
              onChange={(e) => setStop(Number(e.target.value))}
            />
          </Field>
          <Field
            label="If the price rises to… ($)"
            hint="A higher price where you would consider selling to take a gain."
          >
            <input
              required
              type="number"
              min={quote.entry_price + 0.01}
              max={100_000_000}
              step={0.01}
              value={target}
              className={input}
              onChange={(e) => setTarget(Number(e.target.value))}
            />
          </Field>
        </div>
        <p className="text-xs leading-6 text-slate-400">
          The starter values are 3% below and 6% above the buying price. They
          are examples, not advice. A sudden drop can lose more than your plan
          allows.
        </p>
      </div>
      <Field
        label="Why am I trying this, and when will I check it?"
        hint="A quick sentence is enough. This note will help you remember your thinking later."
      >
        <textarea
          required
          rows={2}
          maxLength={2000}
          className={input}
          value={thesis}
          placeholder="I'm trying this idea to see what happens. I'll check it again after the next trading day."
          onChange={(e) => setThesis(e.target.value)}
        />
      </Field>
      <button
        type="button"
        className={button}
        disabled={busy}
        onClick={() => setThesis(starterNote)}
      >
        Use a starter note
      </button>
      <details className="space-y-4">
        <summary className="cursor-pointer text-sm text-indigo-300">
          Help me choose a share count (optional)
        </summary>
        <p className="text-sm leading-6 text-slate-400">
          This works out a share count from the money you are willing to lose at
          your lower sell price, and the balance you can spend. It cannot
          guarantee that loss limit.
        </p>
        <Field label="Part of my pretend balance to risk at that price (%)">
          <input
            type="number"
            min={0.1}
            max={100}
            step={0.1}
            className={`${input} sm:max-w-xs`}
            value={riskPct}
            onChange={(e) => setRiskPct(Number(e.target.value))}
          />
        </Field>
        <button
          type="button"
          className={button}
          disabled={busy}
          onClick={() =>
            setQuantity(
              practiceSize(
                account?.cash ?? 0,
                quote.entry_price,
                stop,
                riskPct,
              ),
            )
          }
        >
          Work out a share count
        </button>
        <p className="text-sm text-slate-400">
          At your lower price, the planned loss would be{" "}
          {money(quantity * (quote.entry_price - stop))}. The actual loss can be
          larger.
        </p>
      </details>
      <details>
        <summary className="cursor-pointer text-sm text-indigo-300">
          Remind me why this stock appeared
        </summary>
        <div className="mt-3">
          <Checks evaluation={quote.evaluation} />
        </div>
      </details>
      <div className="flex flex-wrap gap-2">
        <button className={primary} disabled={busy || expired || !valid}>
          {busy ? "Working…" : "Buy with pretend money"}
        </button>
        <button
          type="button"
          className={button}
          disabled={busy}
          onClick={onRefresh}
        >
          Update price preview
        </button>
      </div>
      {expired ? (
        <p role="status" className="text-sm text-amber-300">
          This preview has expired. Choose “Update price preview”; your plan
          stays here.
        </p>
      ) : (
        <p className="text-xs text-slate-500">
          The price preview lasts two minutes. No real money is used.
        </p>
      )}
      {nextHint && (
        <p role="status" className="text-sm text-amber-300">
          {nextHint}
        </p>
      )}
    </form>
  );
}
