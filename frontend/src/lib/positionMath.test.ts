import { describe, expect, it } from "vitest";
import type { PriceBar } from "../api/client";
import { closestBarOnOrAfter, computePosition } from "./positionMath";

function dailyBars(closes: number[], startDay = 1): PriceBar[] {
  return closes.map((close, i) => ({
    time: `2026-06-${String(startDay + i).padStart(2, "0")}T00:00:00Z`,
    open: close,
    high: close,
    low: close,
    close,
    volume: null,
  }));
}

describe("closestBarOnOrAfter", () => {
  const bars = dailyBars([100, 102, 104], 10); // Jun 10, 11, 12

  it("returns the first bar on/after the date", () => {
    expect(closestBarOnOrAfter(bars, "2026-06-11")?.close).toBe(102);
  });

  it("falls back to the last bar for future dates", () => {
    expect(closestBarOnOrAfter(bars, "2026-07-01")?.close).toBe(104);
  });

  it("returns null on invalid dates or empty history", () => {
    expect(closestBarOnOrAfter(bars, "junk")).toBeNull();
    expect(closestBarOnOrAfter([], "2026-06-11")).toBeNull();
  });
});

describe("computePosition", () => {
  const bars = dailyBars([100, 110, 120], 10); // Jun 10 → 12

  it("uses the manual buy price when provided", () => {
    const calc = computePosition(bars, { amountUsd: 200, buyDate: "2026-06-10", buyPrice: 80 });
    expect(calc).not.toBeNull();
    expect(calc!.buyPrice).toBe(80);
    expect(calc!.shares).toBeCloseTo(2.5);
    expect(calc!.value).toBeCloseTo(300); // 2.5 shares * 120
    expect(calc!.gain).toBeCloseTo(100);
    expect(calc!.returnPct).toBeCloseTo(50);
  });

  it("derives the buy price from the close near the buy date", () => {
    const calc = computePosition(bars, { amountUsd: 100, buyDate: "2026-06-11", buyPrice: null });
    expect(calc!.buyPrice).toBe(110);
    expect(calc!.current).toBe(120);
    expect(calc!.returnPct).toBeCloseTo((120 / 110 - 1) * 100);
  });

  it("flags buy dates older than the available history", () => {
    const calc = computePosition(bars, { amountUsd: 100, buyDate: "2026-01-01", buyPrice: null });
    expect(calc!.datePredatesHistory).toBe(true);
    expect(calc!.buyPrice).toBe(100); // oldest close we have
  });

  it("does not flag manual prices even with an old date", () => {
    const calc = computePosition(bars, { amountUsd: 100, buyDate: "2026-01-01", buyPrice: 90 });
    expect(calc!.datePredatesHistory).toBe(false);
  });

  it("returns null for invalid amounts or missing prices", () => {
    expect(computePosition(bars, { amountUsd: 0, buyDate: "2026-06-10", buyPrice: null })).toBeNull();
    expect(computePosition(bars, { amountUsd: Number.NaN, buyDate: "2026-06-10", buyPrice: null })).toBeNull();
    expect(computePosition([], { amountUsd: 100, buyDate: "2026-06-10", buyPrice: null })).toBeNull();
  });
});
