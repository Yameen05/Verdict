import type { PriceBar } from "../api/client";

export interface PositionInput {
  /** Dollar amount invested. */
  amountUsd: number;
  /** ISO date (YYYY-MM-DD) the user bought. */
  buyDate: string;
  /** Manual buy price; null = derive from the close nearest the buy date. */
  buyPrice: number | null;
}

export interface PositionCalc {
  amount: number;
  buyPrice: number;
  current: number;
  shares: number;
  value: number;
  gain: number;
  returnPct: number;
  /** True when the buy date is older than the available price history, so the
   * derived buy price is only as old as the first bar we have. */
  datePredatesHistory: boolean;
}

export function closestBarOnOrAfter(bars: PriceBar[], date: string): PriceBar | null {
  const target = new Date(`${date}T00:00:00`).getTime();
  if (!Number.isFinite(target)) return null;
  return (
    bars.find((bar) => {
      const day = new Date(bar.time).getTime();
      return Number.isFinite(day) && day >= target;
    }) ??
    bars[bars.length - 1] ??
    null
  );
}

export function computePosition(
  bars: PriceBar[],
  input: PositionInput,
): PositionCalc | null {
  const { amountUsd, buyDate, buyPrice: manualBuy } = input;
  if (!Number.isFinite(amountUsd) || amountUsd <= 0) return null;

  const manualValid = manualBuy !== null && Number.isFinite(manualBuy) && manualBuy > 0;
  const buyBar = manualValid ? null : closestBarOnOrAfter(bars, buyDate);
  const buyPrice = manualValid ? manualBuy : (buyBar?.close ?? null);
  const current = bars[bars.length - 1]?.close ?? null;
  if (!buyPrice || !current) return null;

  const firstBarTime = bars[0] ? new Date(bars[0].time).getTime() : Number.NaN;
  const boughtAt = new Date(`${buyDate}T00:00:00`).getTime();
  const datePredatesHistory =
    !manualValid &&
    Number.isFinite(firstBarTime) &&
    Number.isFinite(boughtAt) &&
    boughtAt < firstBarTime;

  const shares = amountUsd / buyPrice;
  const value = shares * current;
  const gain = value - amountUsd;
  return {
    amount: amountUsd,
    buyPrice,
    current,
    shares,
    value,
    gain,
    returnPct: (gain / amountUsd) * 100,
    datePredatesHistory,
  };
}
