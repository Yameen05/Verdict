import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  userStateApi,
  type PriceBar,
  type ResearchResponse,
  type TimingAssessment,
} from "../api/client";
import { computePosition } from "../lib/positionMath";
import { horizonLabel } from "./VerdictCard";

interface FormState {
  amount: string;
  buyDate: string;
  buyPrice: string;
}

function defaultDate(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

const DEFAULT_FORM: FormState = { amount: "100", buyDate: "", buyPrice: "" };

function money(value: number): string {
  return `$${Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function actionText(
  research: ResearchResponse | null,
  timing: TimingAssessment | null,
): string {
  const rec = research?.report.recommendation;
  const timingAction = timing?.action;
  const horizon = horizonLabel(research?.report.horizon_days ?? null);
  if (rec === "Sell" || timingAction === "avoid") {
    return `Leans sell/avoid right now. If you already own it, consider trimming or exiting unless you have a separate long-term reason to hold. Re-check before holding past ${horizon}.`;
  }
  if (timingAction === "wait_pullback") {
    return `If you already own it, holding can be reasonable; for new money, the timing read says wait for a better entry. Reassess around ${horizon}.`;
  }
  if (rec === "Buy" || timingAction === "buy_now" || timingAction === "accumulate") {
    return `Leans hold/add carefully for this setup. Do not add all at once; reassess around ${horizon} or if the verdict changes.`;
  }
  if (rec === "Hold" || timingAction === "wait_watch") {
    return `Leans hold/watch. The app does not see enough edge to add aggressively or sell urgently. Reassess around ${horizon}.`;
  }
  return "Run Analyze and the timing check to get a sell/hold/add read for this position.";
}

export function PositionTracker({
  ticker,
  research,
  timing,
}: {
  ticker: string;
  research: ResearchResponse | null;
  timing: TimingAssessment | null;
}) {
  const [form, setForm] = useState<FormState>({ ...DEFAULT_FORM, buyDate: defaultDate() });
  const [bars, setBars] = useState<PriceBar[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Saving to the server is debounced and skipped for the initial load.
  const dirtyRef = useRef(false);

  useEffect(() => {
    dirtyRef.current = false;
    setError(null);
    let cancelled = false;
    userStateApi
      .position(ticker)
      .then((res) => {
        if (cancelled) return;
        const saved = res.position;
        setForm(
          saved
            ? {
                amount: String(saved.amount_usd),
                buyDate: saved.buy_date,
                buyPrice: saved.buy_price !== null ? String(saved.buy_price) : "",
              }
            : { ...DEFAULT_FORM, buyDate: defaultDate() },
        );
      })
      .catch(() => {
        if (!cancelled) setForm({ ...DEFAULT_FORM, buyDate: defaultDate() });
      });
    api
      .priceHistory(ticker, "5Y", "1D")
      .then((res) => {
        if (!cancelled) setBars(res.bars);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setBars([]);
          setError(e instanceof Error ? e.message : "Unable to price this position");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  // Persist edits (debounced) so the position follows the user across devices.
  useEffect(() => {
    if (!dirtyRef.current) return;
    const amount = Number(form.amount);
    const buyPrice = Number(form.buyPrice);
    if (!Number.isFinite(amount) || amount <= 0) return;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(form.buyDate)) return;
    const handle = window.setTimeout(() => {
      userStateApi
        .savePosition({
          ticker,
          amount_usd: amount,
          buy_date: form.buyDate,
          buy_price:
            form.buyPrice.trim() !== "" && Number.isFinite(buyPrice) && buyPrice > 0
              ? buyPrice
              : null,
        })
        .catch(() => {
          // Saving is best-effort; the calculation below still works locally.
        });
    }, 600);
    return () => window.clearTimeout(handle);
  }, [form, ticker]);

  const calc = useMemo(() => {
    const manualBuy = Number(form.buyPrice);
    return computePosition(bars, {
      amountUsd: Number(form.amount),
      buyDate: form.buyDate,
      buyPrice:
        form.buyPrice.trim() !== "" && Number.isFinite(manualBuy) && manualBuy > 0
          ? manualBuy
          : null,
    });
  }, [bars, form]);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    dirtyRef.current = true;
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-slate-100">Position tracker</h3>
        <p className="text-[11px] text-slate-500">
          Track what you already bought and translate the verdict into hold/sell/add.
          Saved to your account.
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <label className="text-xs">
          <span className="mb-1 block text-slate-500">Invested</span>
          <input
            value={form.amount}
            onChange={(e) => update("amount", e.target.value)}
            inputMode="decimal"
            className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100 focus:border-cyan-500/70 focus:outline-none"
          />
        </label>
        <label className="text-xs">
          <span className="mb-1 block text-slate-500">Bought on</span>
          <input
            type="date"
            value={form.buyDate}
            onChange={(e) => update("buyDate", e.target.value)}
            className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100 focus:border-cyan-500/70 focus:outline-none"
          />
        </label>
        <label className="text-xs sm:col-span-2">
          <span className="mb-1 block text-slate-500">Buy price, optional</span>
          <input
            value={form.buyPrice}
            onChange={(e) => update("buyPrice", e.target.value)}
            inputMode="decimal"
            placeholder="blank = use close near date"
            className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-slate-100 placeholder:text-slate-600 focus:border-cyan-500/70 focus:outline-none"
          />
        </label>
      </div>

      {error && <p className="mt-3 text-xs text-rose-300">{error}</p>}

      {calc && (
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <Stat label="Value now" value={money(calc.value)} />
          <Stat
            label="Gain / loss"
            value={`${calc.gain >= 0 ? "+" : "-"}${money(calc.gain)}`}
            tone={calc.gain >= 0 ? "good" : "bad"}
          />
          <Stat
            label="Return"
            value={`${calc.returnPct >= 0 ? "+" : ""}${calc.returnPct.toFixed(2)}%`}
            tone={calc.returnPct >= 0 ? "good" : "bad"}
          />
          <Stat label="Shares" value={calc.shares.toFixed(4)} />
        </div>
      )}

      {calc?.datePredatesHistory && (
        <p className="mt-2 text-[11px] text-amber-300/90">
          Your buy date is older than the price history available here, so the
          derived buy price uses the oldest close we have. Enter your actual buy
          price for exact numbers.
        </p>
      )}

      {calc && (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-xs leading-relaxed text-slate-300">
          You bought around <span className="font-semibold text-slate-100">{money(calc.buyPrice)}</span>{" "}
          and it is now around <span className="font-semibold text-slate-100">{money(calc.current)}</span>.{" "}
          {actionText(research, timing)}
          <span className="mt-2 block text-[10px] italic text-slate-500">
            This is a software read of the evidence, not personalized financial
            advice. Only you know your goals, taxes, and risk tolerance.
          </span>
        </div>
      )}
    </section>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "bad";
}) {
  const toneClass =
    tone === "good" ? "text-emerald-300" : tone === "bad" ? "text-rose-300" : "text-slate-100";
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`mt-0.5 text-lg font-bold ${toneClass}`}>{value}</div>
    </div>
  );
}
