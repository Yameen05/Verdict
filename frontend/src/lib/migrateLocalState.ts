import { userStateApi } from "../api/client";

/**
 * One-time migration of workspace state from localStorage to the backend.
 *
 * Earlier versions kept the watchlist, price alerts, positions, chart levels,
 * and verdict watches in this browser only. Each key is pushed to the server
 * once and then removed; a failed push keeps the key so the next app load
 * retries. Safe to call on every startup — with nothing left to migrate it
 * does no network calls.
 */
export async function migrateLocalStateOnce(): Promise<void> {
  await migrateWatchlist();
  await migrateAlerts();
  await migratePositions();
  await migrateLevels();
  await migrateVerdictWatches();
}

function readJson<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function removeKey(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // localStorage unavailable — nothing to migrate anyway.
  }
}

async function migrateWatchlist(): Promise<void> {
  const list = readJson<string[]>("verdict.watchlist");
  if (!Array.isArray(list)) return;
  try {
    for (const ticker of list.filter((t) => typeof t === "string" && t)) {
      await userStateApi.addWatchlist(ticker);
    }
    removeKey("verdict.watchlist");
  } catch {
    // Server unavailable — retry on next load.
  }
}

interface LegacyAlert {
  ticker: string;
  direction: "above" | "below";
  price: number;
  triggered?: boolean;
}

async function migrateAlerts(): Promise<void> {
  const alerts = readJson<LegacyAlert[]>("verdict.alerts");
  if (!Array.isArray(alerts)) return;
  try {
    for (const alert of alerts) {
      // Skip already-triggered alerts: recreating them server-side would
      // re-fire notifications for old crossings.
      if (!alert || alert.triggered || typeof alert.price !== "number") continue;
      if (alert.direction !== "above" && alert.direction !== "below") continue;
      await userStateApi.createAlert(alert.ticker, alert.direction, alert.price);
    }
    removeKey("verdict.alerts");
  } catch {
    // Retry on next load.
  }
}

interface LegacyPosition {
  ticker: string;
  amount: string;
  buyDate: string;
  buyPrice: string;
}

async function migratePositions(): Promise<void> {
  const positions = readJson<Record<string, LegacyPosition>>("verdict.positions");
  if (!positions || typeof positions !== "object") return;
  try {
    for (const saved of Object.values(positions)) {
      const amount = Number(saved?.amount);
      const buyPrice = Number(saved?.buyPrice);
      if (!saved?.ticker || !Number.isFinite(amount) || amount <= 0) continue;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(saved.buyDate ?? "")) continue;
      await userStateApi.savePosition({
        ticker: saved.ticker,
        amount_usd: amount,
        buy_date: saved.buyDate,
        buy_price: Number.isFinite(buyPrice) && buyPrice > 0 ? buyPrice : null,
      });
    }
    removeKey("verdict.positions");
  } catch {
    // Retry on next load.
  }
}

async function migrateLevels(): Promise<void> {
  const prefix = "verdict.levels.";
  let keys: string[] = [];
  try {
    keys = Object.keys(window.localStorage).filter((k) => k.startsWith(prefix));
  } catch {
    return;
  }
  for (const key of keys) {
    const prices = readJson<number[]>(key);
    const ticker = key.slice(prefix.length);
    if (!Array.isArray(prices) || !ticker) {
      removeKey(key);
      continue;
    }
    try {
      for (const price of prices.filter((p) => typeof p === "number" && p > 0)) {
        await userStateApi.addLevel(ticker, price);
      }
      removeKey(key);
    } catch {
      // Retry on next load.
    }
  }
}

async function migrateVerdictWatches(): Promise<void> {
  const watches = readJson<Record<string, string>>("verdict.verdictWatch");
  if (!watches || typeof watches !== "object") return;
  try {
    for (const [ticker, recommendation] of Object.entries(watches)) {
      if (typeof recommendation !== "string" || !recommendation) continue;
      await userStateApi.setVerdictWatch(ticker, recommendation);
    }
    removeKey("verdict.verdictWatch");
  } catch {
    // Retry on next load.
  }
}
