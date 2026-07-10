import { describe, expect, it } from "vitest";
import type { HistoryEntry, PriceBar } from "../../api/client";
import {
  bollingerBands,
  macdSeries,
  mergeLiveBar,
  movingAverage,
  rsiSeries,
  toPercentSeries,
  toTimestamp,
  verdictMarkers,
} from "./chartMath";

function dailyBars(closes: number[], startDay = 1): PriceBar[] {
  return closes.map((close, i) => ({
    time: `2026-01-${String(startDay + i).padStart(2, "0")}T00:00:00Z`,
    open: close,
    high: close + 1,
    low: close - 1,
    close,
    volume: 1000,
  }));
}

describe("movingAverage", () => {
  it("averages the trailing window", () => {
    const out = movingAverage(dailyBars([1, 2, 3, 4, 5]), 2);
    expect(out.map((p) => p.value)).toEqual([1.5, 2.5, 3.5, 4.5]);
  });

  it("returns nothing when there are fewer bars than the window", () => {
    expect(movingAverage(dailyBars([1, 2]), 5)).toEqual([]);
  });
});

describe("bollingerBands", () => {
  it("collapses to the basis when prices are flat", () => {
    const { basis, upper, lower } = bollingerBands(dailyBars(Array(25).fill(50)), 20, 2);
    expect(basis.length).toBe(6);
    expect(upper[0].value).toBe(50);
    expect(lower[0].value).toBe(50);
    expect(basis[0].value).toBe(50);
  });

  it("puts upper above and lower below the basis when prices vary", () => {
    const closes = Array.from({ length: 25 }, (_, i) => 50 + (i % 2 ? 5 : -5));
    const { basis, upper, lower } = bollingerBands(dailyBars(closes), 20, 2);
    expect(upper[0].value).toBeGreaterThan(basis[0].value);
    expect(lower[0].value).toBeLessThan(basis[0].value);
  });
});

describe("rsiSeries", () => {
  it("reads 100 when every day is a gain", () => {
    const closes = Array.from({ length: 20 }, (_, i) => 100 + i);
    const out = rsiSeries(dailyBars(closes), 14);
    expect(out.length).toBe(20 - 14);
    expect(out[out.length - 1].value).toBe(100);
  });

  it("stays within 0..100 on mixed data", () => {
    const closes = Array.from({ length: 30 }, (_, i) => 100 + Math.sin(i) * 10);
    for (const point of rsiSeries(dailyBars(closes), 14)) {
      expect(point.value).toBeGreaterThanOrEqual(0);
      expect(point.value).toBeLessThanOrEqual(100);
    }
  });

  it("returns nothing without period+1 bars", () => {
    expect(rsiSeries(dailyBars([1, 2, 3]), 14)).toEqual([]);
  });
});

describe("macdSeries", () => {
  it("histogram equals macd minus signal, and rises in an uptrend", () => {
    // Needs ≥ slow(26) + signal(9) bars for the signal EMA to exist. Use
    // timestamps via an epoch offset to stay within real calendar days.
    const closes = Array.from({ length: 60 }, (_, i) => 100 + i * 2);
    const bars = closes.map((close, i) => ({
      time: new Date(Date.UTC(2026, 0, 1 + i)).toISOString(),
      open: close,
      high: close + 1,
      low: close - 1,
      close,
      volume: 1000,
    }));
    const { macd, signal, histogram } = macdSeries(bars);
    expect(macd.length).toBeGreaterThan(0);
    expect(signal.length).toBe(histogram.length);
    const lastMacd = macd[macd.length - 1].value;
    const lastSignal = signal[signal.length - 1].value;
    const lastHist = histogram[histogram.length - 1].value;
    expect(lastHist).toBeCloseTo(lastMacd - lastSignal, 3);
    expect(lastMacd).toBeGreaterThan(0);
  });
});

describe("toPercentSeries", () => {
  it("rebases to percent change from the first positive close", () => {
    const out = toPercentSeries(dailyBars([100, 110, 90]));
    expect(out.map((p) => p.value)).toEqual([0, 10, -10]);
  });

  it("returns empty when no positive close exists", () => {
    expect(toPercentSeries([])).toEqual([]);
  });
});

describe("mergeLiveBar", () => {
  const bars = dailyBars([10, 11, 12]);

  it("replaces the last bar on a matching timestamp", () => {
    const next = { ...bars[2], close: 99 };
    const merged = mergeLiveBar(bars, next);
    expect(merged.length).toBe(3);
    expect(merged[2].close).toBe(99);
  });

  it("appends a newer bar", () => {
    const next = { ...bars[2], time: "2026-01-04T00:00:00Z" };
    expect(mergeLiveBar(bars, next).length).toBe(4);
  });

  it("patches a matching historical bar in place", () => {
    const next = { ...bars[1], close: 55 };
    const merged = mergeLiveBar(bars, next);
    expect(merged.length).toBe(3);
    expect(merged[1].close).toBe(55);
  });

  it("starts a series from empty", () => {
    expect(mergeLiveBar([], bars[0])).toEqual([bars[0]]);
  });
});

describe("verdictMarkers", () => {
  const bars = dailyBars([10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);

  function entry(created_at: string, recommendation: HistoryEntry["recommendation"]): HistoryEntry {
    return {
      id: 1,
      ticker: "AAPL",
      recommendation,
      justification: "",
      sentiment_score: null,
      confidence: 80,
      price_at_run: null,
      duration_ms: null,
      cost_usd: null,
      created_at,
    };
  }

  it("snaps a verdict to the first bar at/after its time", () => {
    const markers = verdictMarkers([entry("2026-01-03T12:00:00Z", "Buy")], bars);
    expect(markers.length).toBe(1);
    expect(markers[0].time).toBe(toTimestamp("2026-01-04T00:00:00Z"));
    expect(markers[0].text).toBe("Buy 80");
  });

  it("drops verdicts outside the visible range and skips Pending", () => {
    const markers = verdictMarkers(
      [entry("2025-12-01T00:00:00Z", "Buy"), entry("2026-01-05T00:00:00Z", "Pending")],
      bars,
    );
    expect(markers).toEqual([]);
  });

  it("sorts markers ascending by time", () => {
    const markers = verdictMarkers(
      [entry("2026-01-08T00:00:00Z", "Sell"), entry("2026-01-02T00:00:00Z", "Buy")],
      bars,
    );
    expect(markers.map((m) => m.text)).toEqual(["Buy 80", "Sell 80"]);
  });
});
