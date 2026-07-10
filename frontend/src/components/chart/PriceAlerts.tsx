import { useCallback, useEffect, useRef, useState } from "react";
import { userStateApi, type ServerAlert } from "../../api/client";

type Direction = "above" | "below";

function notify(alert: ServerAlert, price: number): void {
  const body = `${alert.ticker} is ${alert.direction} $${alert.price.toLocaleString()} (now $${price.toFixed(2)})`;
  if (typeof Notification !== "undefined" && Notification.permission === "granted") {
    new Notification("Verdict price alert", { body });
  }
}

/**
 * Price alerts, stored server-side (see routers/user_state.py). A background
 * worker evaluates them even when no tab is open; this component additionally
 * watches the chart's live price so an alert crossing you're looking at fires
 * a browser notification instantly instead of on the next worker cycle.
 */
export function PriceAlerts({ ticker, price }: { ticker: string; price: number | null }) {
  const [alerts, setAlerts] = useState<ServerAlert[]>([]);
  const [draftPrice, setDraftPrice] = useState("");
  const [direction, setDirection] = useState<Direction>("above");
  const [justTriggered, setJustTriggered] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const alertsRef = useRef(alerts);
  alertsRef.current = alerts;

  const refresh = useCallback(() => {
    userStateApi
      .alerts()
      .then((res) => {
        setAlerts(res.alerts);
        setError(null);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Alerts unavailable"),
      );
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener("verdict-alerts-updated", refresh);
    return () => window.removeEventListener("verdict-alerts-updated", refresh);
  }, [refresh]);

  // Instant client-side check on every live price tick. The server worker is
  // the source of truth; this just makes the visible tab feel immediate.
  useEffect(() => {
    if (price === null) return;
    for (const alert of alertsRef.current) {
      if (alert.triggered || alert.ticker !== ticker) continue;
      const crossed =
        alert.direction === "above" ? price >= alert.price : price <= alert.price;
      if (!crossed) continue;
      notify(alert, price);
      setJustTriggered((prev) => [...prev, alert.id]);
      window.setTimeout(
        () => setJustTriggered((prev) => prev.filter((id) => id !== alert.id)),
        6000,
      );
      userStateApi
        .triggerAlert(alert.id)
        .then(() => refresh())
        .catch(() => refresh());
    }
  }, [price, refresh, ticker]);

  const addAlert = useCallback(async () => {
    const value = Number(draftPrice);
    if (!Number.isFinite(value) || value <= 0) return;
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      await Notification.requestPermission();
    }
    try {
      await userStateApi.createAlert(ticker, direction, Number(value.toFixed(2)));
      setDraftPrice("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save alert");
    }
  }, [draftPrice, direction, refresh, ticker]);

  const removeAlert = useCallback(
    (id: number) => {
      userStateApi
        .deleteAlert(id)
        .then(() => refresh())
        .catch((e: unknown) =>
          setError(e instanceof Error ? e.message : "Could not remove alert"),
        );
    },
    [refresh],
  );

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
        <span className="text-[10px] text-slate-600">
          checked in the background, even with the app closed
        </span>
        {error && <span className="text-xs text-rose-300">{error}</span>}
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
