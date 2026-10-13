import { useState } from "react";
import type { Account, Trade } from "../../api/practice";
import { ideaFor } from "../../lib/practiceGuide";
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

function PracticeHolding({
  trade,
  account,
  name,
  busy,
  onSell,
  onSave,
  onResearch,
}: {
  trade: Trade;
  account: Account;
  name: string;
  busy: boolean;
  onSell: () => void;
  onSave: (notes: string) => void;
  onResearch: () => void;
}) {
  const [notes, setNotes] = useState(trade.notes);
  const raw = account.marks[trade.ticker];
  const mark =
    raw?.as_of && asOf(raw.as_of) < asOf(trade.context.evaluation.as_of)
      ? {
          reason: "We need a price at least as recent as the one you bought at",
          price: undefined,
          as_of: undefined,
        }
      : raw;
  const result = trade.closed_at
    ? trade.realized_pnl
    : mark?.price != null
      ? (mark.price - trade.entry_price) * trade.quantity
      : null;
  return (
    <article className={`${panel} space-y-4`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xl text-slate-100">{name}</h3>
          <p className="mt-1 text-sm text-slate-400">
            {trade.ticker} · {trade.quantity}{" "}
            {trade.quantity === 1 ? "share" : "shares"} ·{" "}
            {trade.closed_at
              ? "Sold — result saved"
              : "You still own these practice shares"}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-400">
            {trade.closed_at
              ? "Gain or loss after selling"
              : "Change so far — could still change"}
          </p>
          <p
            className={`mt-1 font-mono text-xl ${result == null ? "text-slate-400" : result >= 0 ? "text-emerald-300" : "text-rose-300"}`}
          >
            {money(result)}
          </p>
        </div>
      </div>
      <p className="text-sm leading-6 text-slate-300">
        You bought {trade.quantity} at {money(trade.entry_price)} each.{" "}
        {trade.closed_at
          ? `You sold at ${money(trade.exit_price)} each, returning ${money((trade.exit_price ?? 0) * trade.quantity)} to your pretend balance.`
          : mark?.price != null
            ? `The latest recorded price is ${money(mark.price)} each.`
            : `We cannot show a current value: ${mark?.reason ?? "prices are not available yet"}.`}
      </p>
      <p className="text-xs leading-6 text-slate-400">
        Bought on {new Date(trade.opened_at).toLocaleDateString()} using the
        price from {asOf(trade.context.evaluation.as_of)}.
        {trade.closed_at
          ? ` Sold on ${new Date(trade.closed_at).toLocaleDateString()} using the price from ${asOf(trade.exit_as_of!)}.`
          : mark?.as_of
            ? ` Latest recorded price: ${asOf(mark.as_of)}.`
            : ""}
      </p>
      {!trade.closed_at && (
        <div className="space-y-2 rounded-xl border border-slate-700 p-4">
          <p className="text-sm leading-6 text-slate-300">
            When you want to finish this practice try, sell your shares. Their
            value goes back into your pretend balance, and the result stays in
            your notes below.
          </p>
          <button
            className={primary}
            disabled={busy || mark?.price == null}
            onClick={onSell}
          >
            Sell my practice shares
          </button>
          <PriceNote />
        </div>
      )}
      <details>
        <summary className="cursor-pointer text-sm text-indigo-300">
          What was my idea and sell plan?
        </summary>
        <div className="mt-3 space-y-3 text-sm leading-6 text-slate-400">
          <p className="text-slate-200">{trade.context.plan.thesis}</p>
          <p>
            Saved search: {trade.context.strategy.name}
            <br />
            Starting idea: {ideaFor(trade.context.strategy.template).name}
          </p>
          <p>
            You planned to consider selling if the price fell to{" "}
            {money(trade.context.plan.stop)} or rose to{" "}
            {money(trade.context.plan.target)}. These were reminders; selling
            was always up to you.
          </p>
          <p>
            At those prices, the planned loss was{" "}
            {money(trade.context.plan.risk_usd)}, or the planned gain was{" "}
            {money(trade.context.plan.reward_usd)}. Those amounts were not
            guaranteed.
          </p>
          <p>
            {trade.context.evaluation.matched
              ? "This stock fitted every condition when you bought it."
              : "This stock did not fit every condition when you bought it."}{" "}
            This is your original saved plan, even if you change the search
            later.
          </p>
          <p className="text-xs">
            Bought {new Date(trade.opened_at).toLocaleString()}.
            {trade.closed_at
              ? ` Sold ${new Date(trade.closed_at).toLocaleString()}.`
              : ""}
          </p>
          <Checks evaluation={trade.context.evaluation} />
          <details>
            <summary className="cursor-pointer text-xs">
              Original number settings
            </summary>
            <p>
              {trade.context.strategy.template === "rsi_recovery"
                ? `Price-change measure: RSI over 14 trading days, recovery line ${trade.context.strategy.rsi_threshold}.`
                : `Price comparison: ${trade.context.strategy.lookback} trading days.`}{" "}
              {trade.context.strategy.template === "breakout"
                ? `Trading amount: ${trade.context.strategy.volume_multiple} times usual.`
                : trade.context.strategy.template === "pullback"
                  ? `Allowed distance from the average: ${trade.context.strategy.tolerance_pct}%.`
                  : ""}
            </p>
          </details>
        </div>
      </details>
      <Field
        label="What happened? What would I try next time?"
        hint="Your notes are for learning. You can come back and change them."
      >
        <textarea
          className={input}
          maxLength={4000}
          rows={2}
          value={notes}
          placeholder="Did the price move how I expected? Did I follow my sell plan?"
          onChange={(e) => setNotes(e.target.value)}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <button
          className={button}
          disabled={busy || notes === trade.notes}
          onClick={() => onSave(notes)}
        >
          Save my notes
        </button>
        <button className={button} disabled={busy} onClick={onResearch}>
          Read more in Research
        </button>
      </div>
      <p className="text-xs text-slate-500">
        Opening Research is free. AI research starts only if you choose Analyze
        there.
      </p>
    </article>
  );
}
export function PracticeJournal({
  account,
  busy,
  nameFor,
  onRefresh,
  onStart,
  onSell,
  onSave,
  onResearch,
}: {
  account: Account | null;
  busy: boolean;
  nameFor: (ticker: string) => string;
  onRefresh: () => void;
  onStart: () => void;
  onSell: (trade: Trade) => void;
  onSave: (trade: Trade, notes: string) => void;
  onResearch: (ticker: string) => void;
}) {
  return (
    <section className="space-y-5">
      <header>
        <p className="text-sm text-indigo-300">Step 5 · See what happened</p>
        <h2 className="mt-1 font-display text-2xl text-slate-100">
          Your pretend money & notes
        </h2>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
          You start with $100,000 pretend money. Buying shares takes money from
          your balance; selling puts their value back. The difference is your
          gain or loss.
        </p>
      </header>
      {!account ? (
        <div className={`${panel} space-y-3`}>
          <p>Loading your pretend money…</p>
          <button className={button} disabled={busy} onClick={onRefresh}>
            Try loading again
          </button>
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              [
                "Pretend money left to spend",
                account.cash,
                "What you can use to buy more practice shares.",
              ],
              [
                "Money + shares you still own",
                account.equity,
                "Your remaining money plus the value of your shares at the recorded prices.",
              ],
            ].map(([label, value, hint]) => (
              <div className={panel} key={String(label)}>
                <p className="text-sm text-slate-300">{label}</p>
                <p className="mt-2 font-mono text-2xl text-slate-100">
                  {money(value as number | null)}
                </p>
                <p className="mt-2 text-xs leading-5 text-slate-400">{hint}</p>
              </div>
            ))}
          </div>
          <details className={panel}>
            <summary className="cursor-pointer text-sm text-slate-300">
              See my total gains and losses
            </summary>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <p className="text-sm text-slate-400">
                From shares you have sold
                <strong className="mt-1 block font-mono text-lg text-slate-100">
                  {money(account.realized_pnl)}
                </strong>
              </p>
              <p className="text-sm text-slate-400">
                Change on shares you still own
                <strong className="mt-1 block font-mono text-lg text-slate-100">
                  {money(account.unrealized_pnl)}
                </strong>
                <span className="text-xs">
                  This can change before you sell.
                </span>
              </p>
            </div>
          </details>
          {account.equity == null && (
            <p className="text-sm text-amber-300">
              Some prices are missing. We will show your shares' value and total
              when recent prices are available.
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button className={button} disabled={busy} onClick={onRefresh}>
              Check for newer prices
            </button>
            <button className={button} disabled={busy} onClick={onStart}>
              Find another stock to try
            </button>
          </div>
          <PriceNote />
          {account.trades.length === 0 && (
            <div className={`${panel} space-y-3`}>
              <h3 className="text-lg text-slate-100">
                You have not tried buying shares yet
              </h3>
              <p className="text-sm leading-6 text-slate-400">
                Pick a starting idea, find a stock that fits, then try buying
                one share with pretend money. Nothing here uses real money.
              </p>
              <button className={primary} disabled={busy} onClick={onStart}>
                Choose my first idea
              </button>
            </div>
          )}
          {([false, true] as const).map((closed) => {
            const trades = account.trades.filter(
              (t) => Boolean(t.closed_at) === closed,
            );
            return (
              trades.length > 0 && (
                <div className="space-y-4" key={String(closed)}>
                  <h3 className="font-display text-xl text-slate-100">
                    {closed
                      ? "Shares you sold — your results"
                      : "Practice shares you still own"}{" "}
                    ({trades.length})
                  </h3>
                  {trades.map((trade) => (
                    <PracticeHolding
                      key={trade.id}
                      trade={trade}
                      account={account}
                      name={nameFor(trade.ticker)}
                      busy={busy}
                      onSell={() => onSell(trade)}
                      onSave={(notes) => onSave(trade, notes)}
                      onResearch={() => onResearch(trade.ticker)}
                    />
                  ))}
                </div>
              )
            );
          })}
        </>
      )}
      <details>
        <summary className="cursor-pointer text-xs text-slate-500">
          How this practice account works
        </summary>
        <p className="mt-2 max-w-3xl text-xs leading-6 text-slate-400">
          You buy whole shares using the pretend balance, without borrowing
          money. This simple version leaves out trading costs, differences
          between the shown price and an actual purchase, payouts from
          companies, and changes such as share splits. Your lower and higher
          sell prices do not sell automatically. These practice results are
          separate from Track record, which checks Verdict's AI research calls.
        </p>
      </details>
    </section>
  );
}
