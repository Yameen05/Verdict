import { useEffect, useMemo, useState } from "react";
import {
  userStateApi,
  type AssetCapabilities,
  type ResearchResponse,
  type TimingAssessment,
} from "../api/client";
import { InfoTip } from "./InfoTip";

function numberFrom(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function SmartAlertsPanel({
  ticker,
  research,
  timing,
  livePrice,
  capabilities,
}: {
  ticker: string;
  research: ResearchResponse | null;
  timing: TimingAssessment | null;
  livePrice: number | null;
  capabilities: AssetCapabilities | null;
}) {
  const [watchedRec, setWatchedRec] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The chart's live poll is the freshest price; research metrics can be
  // hours old (they're from the last Analyze run).
  const currentPrice =
    livePrice ??
    numberFrom(timing?.technicals.close) ??
    research?.metrics.current_price ??
    research?.signals.quotes.find((q) => q.price !== null)?.price ??
    null;
  const currentRec = research?.report.recommendation ?? null;
  const verdictChanged = Boolean(currentRec && watchedRec && currentRec !== watchedRec);
  const target = research?.signals.fundamentals?.analyst_target ?? null;
  const earningsDays = research?.signals.earnings_days ?? null;
  const showEarnings = earningsDays !== null && capabilities?.has_earnings !== false;

  useEffect(() => {
    let cancelled = false;
    setSaved(null);
    setError(null);
    userStateApi
      .verdictWatch(ticker)
      .then((res) => {
        if (!cancelled) setWatchedRec(res.recommendation);
      })
      .catch(() => {
        if (!cancelled) setWatchedRec(null);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const entryDirection = useMemo(() => {
    if (!timing || currentPrice === null) return null;
    const low = timing.entry_zone_low;
    const high = timing.entry_zone_high;
    if (low === null || high === null) return null;
    if (currentPrice > high) return { direction: "below" as const, price: high };
    if (currentPrice < low) return { direction: "above" as const, price: low };
    return null;
  }, [currentPrice, timing]);

  function armVerdictWatch() {
    if (!currentRec) return;
    userStateApi
      .setVerdictWatch(ticker, currentRec)
      .then((res) => {
        setWatchedRec(res.recommendation);
        setSaved(`Watching for a verdict change from ${res.recommendation}`);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Could not save the watch"),
      );
  }

  function quickAlert(label: string, direction: "above" | "below", price: number) {
    userStateApi
      .createAlert(ticker, direction, Number(price.toFixed(2)))
      .then(() => {
        setSaved(`${label} alert saved at $${price.toFixed(2)}`);
        setError(null);
        window.dispatchEvent(new Event("verdict-alerts-updated"));
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Could not save the alert"),
      );
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
      <h3 className="text-sm font-semibold text-slate-100">
        Smart alerts
        <InfoTip label="Smart alerts">
          Alerts are saved to your account and checked by the server even when
          the app is closed (email arrives if the owner configured SMTP). Price
          alerts also appear under the chart.
        </InfoTip>
      </h3>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={armVerdictWatch}
          disabled={!currentRec}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-900 disabled:opacity-50"
        >
          {watchedRec ? `Watching (${watchedRec})` : "Watch verdict change"}
        </button>
        {entryDirection && (
          <button
            type="button"
            onClick={() => quickAlert("Entry zone", entryDirection.direction, entryDirection.price)}
            className="rounded-md border border-cyan-500/50 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/20"
          >
            Alert at entry zone
          </button>
        )}
        {target !== null && currentPrice !== null && capabilities?.has_analyst_coverage !== false && (
          <button
            type="button"
            onClick={() => quickAlert("Analyst target", currentPrice < target ? "above" : "below", target)}
            className="rounded-md border border-fuchsia-500/50 bg-fuchsia-500/10 px-3 py-1.5 text-xs font-semibold text-fuchsia-200 hover:bg-fuchsia-500/20"
          >
            Alert at target
          </button>
        )}
        {currentPrice !== null && (
          <>
            <button
              type="button"
              onClick={() => quickAlert("+5% move", "above", currentPrice * 1.05)}
              className="rounded-md border border-emerald-500/50 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/20"
            >
              Alert +5%
            </button>
            <button
              type="button"
              onClick={() => quickAlert("-5% move", "below", currentPrice * 0.95)}
              className="rounded-md border border-rose-500/50 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-200 hover:bg-rose-500/20"
            >
              Alert -5%
            </button>
          </>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        {verdictChanged && (
          <span className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-amber-200">
            Verdict changed: {watchedRec} to {currentRec}
          </span>
        )}
        {showEarnings && (
          <span
            className={`rounded-md border px-2 py-1 ${
              earningsDays <= 3
                ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
                : "border-slate-700 bg-slate-900 text-slate-400"
            }`}
          >
            Earnings in ~{earningsDays} day(s)
          </span>
        )}
        {saved && (
          <span className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-1 text-emerald-200">
            {saved}
          </span>
        )}
        {error && (
          <span className="rounded-md border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-rose-200">
            {error}
          </span>
        )}
      </div>
    </section>
  );
}
