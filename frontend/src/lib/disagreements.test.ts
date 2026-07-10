import { describe, expect, it } from "vitest";
import type { ResearchResponse, TimingAssessment } from "../api/client";
import { buildDisagreements, timingLean, verdictLean } from "./disagreements";

/** Minimal research fixture — only fields buildDisagreements reads. */
function research(overrides: {
  recommendation?: string;
  analyst?: { score: number; consensus: string } | null;
  retail?: { score: number; sample: number; label: string } | null;
  macro?: { regime: string } | null;
  earnings_days?: number | null;
}): ResearchResponse {
  return {
    report: { recommendation: overrides.recommendation ?? "Buy" },
    signals: {
      analyst: overrides.analyst ?? null,
      retail: overrides.retail ?? null,
      macro: overrides.macro ?? null,
      earnings_days: overrides.earnings_days ?? null,
    },
  } as unknown as ResearchResponse;
}

function timing(action: TimingAssessment["action"], label = action): TimingAssessment {
  return { action, action_label: label } as unknown as TimingAssessment;
}

describe("leans", () => {
  it("maps verdicts and timing actions onto the same -1/0/1 axis", () => {
    expect(verdictLean("Buy")).toBe(1);
    expect(verdictLean("Sell")).toBe(-1);
    expect(verdictLean("Hold")).toBe(0);
    expect(timingLean("buy_now")).toBe(1);
    expect(timingLean("accumulate")).toBe(1);
    expect(timingLean("avoid")).toBe(-1);
    expect(timingLean("wait_watch")).toBe(0);
    expect(timingLean(undefined)).toBe(0);
  });
});

describe("buildDisagreements", () => {
  it("returns nothing without research", () => {
    expect(buildDisagreements(null, null)).toEqual([]);
  });

  it("flags analysts pushing against the verdict", () => {
    const out = buildDisagreements(
      research({ recommendation: "Sell", analyst: { score: 0.5, consensus: "Buy" } }),
      null,
    );
    expect(out.map((d) => d.title)).toContain("Analysts disagree with the verdict");
  });

  it("ignores weak or aligned analyst signals", () => {
    const weak = buildDisagreements(
      research({ recommendation: "Sell", analyst: { score: 0.1, consensus: "Hold" } }),
      null,
    );
    const aligned = buildDisagreements(
      research({ recommendation: "Buy", analyst: { score: 0.5, consensus: "Buy" } }),
      null,
    );
    expect(weak).toEqual([]);
    expect(aligned).toEqual([]);
  });

  it("requires a minimum retail sample before flagging", () => {
    const small = buildDisagreements(
      research({ recommendation: "Buy", retail: { score: -0.6, sample: 3, label: "bearish" } }),
      null,
    );
    const enough = buildDisagreements(
      research({ recommendation: "Buy", retail: { score: -0.6, sample: 10, label: "bearish" } }),
      null,
    );
    expect(small).toEqual([]);
    expect(enough.map((d) => d.title)).toContain("Retail sentiment disagrees");
  });

  it("flags timing vs verdict conflicts and the wait-for-pullback nuance", () => {
    const conflict = buildDisagreements(research({ recommendation: "Buy" }), timing("avoid"));
    expect(conflict.map((d) => d.title)).toContain("Timing and verdict disagree");

    const pullback = buildDisagreements(
      research({ recommendation: "Buy" }),
      timing("wait_pullback"),
    );
    expect(pullback.map((d) => d.title)).toContain("Bullish, but not at any price");
  });

  it("flags macro headwind and imminent earnings only on Buy", () => {
    const buy = buildDisagreements(
      research({ recommendation: "Buy", macro: { regime: "restrictive" }, earnings_days: 3 }),
      null,
    );
    expect(buy.map((d) => d.title)).toEqual(
      expect.arrayContaining(["Macro is a headwind", "Earnings are close"]),
    );

    const hold = buildDisagreements(
      research({ recommendation: "Hold", macro: { regime: "restrictive" }, earnings_days: 3 }),
      null,
    );
    expect(hold).toEqual([]);
  });

  it("caps the list at four items", () => {
    const out = buildDisagreements(
      research({
        recommendation: "Buy",
        analyst: { score: -0.5, consensus: "Sell" },
        retail: { score: -0.6, sample: 10, label: "bearish" },
        macro: { regime: "restrictive" },
        earnings_days: 2,
      }),
      timing("avoid"),
    );
    expect(out.length).toBe(4);
  });
});
