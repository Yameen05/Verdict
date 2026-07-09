import { useCallback, useEffect, useRef, useState } from "react";

type Direction = "above" | "below";

interface Alert {
  id: string;
  ticker: string;
  direction: Direction;
  price: number;
  createdAt: string;
  triggered: boolean;
}

const STORAGE_KEY = "verdict.alerts";

function loadAlerts(): Alert[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Alert[]) : [];
  } catch {
    return [];
  }
}

function saveAlerts(alerts: Alert[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(alerts));
  } catch {
    // localStorage unavailable — alerts persist for this session only.
  }
}

function notify(alert: Alert, price: number): void {
  const body = `${alert.ticker} is ${alert.direction} $${alert.price.toLocaleString()} (now $${price.toFixed(2)})`;
  if (typeof Notification !== "undefined" && Notification.permission === "granted") {
    new Notification("Verdict price alert", { body });
  }
}

/**
 * Client-side price alerts (#4). Watches the live price coming from the chart's
 * existing poll and fires a browser notification when a threshold is crossed —
 * no backend/push infrastructure needed while the tab is open.
 */
export function PriceAlerts({ ticker, price }: { ticker: string; price: number | null }) {
  const [alerts, setAlerts] = useState<Alert[]>(loadAlerts);
  const [draftPrice, setDraftPrice] = useState("");
  const [direction, setDirection] = useState<Direction>("above");
  const [justTriggered, setJustTriggered] = useState<string[]>([]);
  const alertsRef = useRef(alerts);
  alertsRef.current = alerts;

  useEffect(() => {
    saveAlerts(alerts);
  }, [alerts]);

  // Evaluate on every price tick; mark crossed alerts triggered exactly once.
  useEffect(() => {
    if (price === null) return;
    const fired: string[] = [];
    const next = alertsRef.current.map((a) => {
      if (a.triggered || a.ticker !== ticker) return a;
      const crossed = a.direction === "above" ? price >= a.price : price <= a.price;
      if (crossed) {
        notify(a, price);
        fired.push(a.id);
        return { ...a, triggered: true };
      }
      return a;
    });
    if (fired.length) {
      setAlerts(next);
      setJustTriggered(fired);
      window.setTimeout(() => setJustTriggered([]), 6000);
    }
  }, [price, ticker]);

  const addAlert = useCallback(async () => {
    const value = Number(draftPrice);
    if (!Number.isFinite(value) || value <= 0) return;
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      await Notification.requestPermission();
    }
    setAlerts((prev) => [
      ...prev,
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        ticker,
        direction,
        price: Number(value.toFixed(2)),
        createdAt: new Date().toISOString(),
        triggered: false,
      },
    ]);
    setDraftPrice("");
  }, [draftPrice, direction, ticker]);

  const removeAlert = useCallback((id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const forTicker = alerts.filter((a) => a.ticker === ticker);

  return (
    <div className="border-t border-slate-800 bg-slate-950/90 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Alerts
        </span>
        <div className="flex overflow-hidden rounded-md border border-slate-800">
          {(["above", "below"] as Direction[]).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDirection(d)}
              className={`px-2.5 py-1 text-xs font-semibold capitalize transition ${
                direction === d
                  ? "bg-slate-100 text-slate-950"
                  : "bg-slate-900 text-slate-400 hover:text-slate-100"
              }`}
            >
              {d}
            </button>
          ))}
        </div>
        <input
          value={draftPrice}
          onChange={(e) => setDraftPrice(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void addAlert();
          }}
          inputMode="decimal"
          placeholder="price"
          className="w-24 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs font-medium text-slate-100 placeholder:text-slate-600 focus:border-cyan-500/60 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => void addAlert()}
          className="rounded-md border border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 hover:border-slate-500 hover:bg-slate-900"
        >
          Set alert
        </button>
      </div>

      {forTicker.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {forTicker.map((a) => (
            <span
              key={a.id}
              className={`flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium ${
                a.triggered
                  ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                  : justTriggered.includes(a.id)
                    ? "border-amber-500/50 bg-amber-500/10 text-amber-200"
                    : "border-slate-700 bg-slate-900 text-slate-300"
              }`}
            >
              {a.triggered ? "✓ " : ""}
              {a.direction === "above" ? "≥" : "≤"} ${a.price.toLocaleString()}
              <button
                type="button"
                onClick={() => removeAlert(a.id)}
                className="text-slate-500 hover:text-slate-200"
                aria-label="Remove alert"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
