import { describe, expect, it } from "vitest";
import { progressPercent, timeRemaining, utcDate } from "./trackRecord";
import type { ScoreboardEntry } from "../api/types";

const entry = {
  created_at: "2026-10-10T18:00:00", due_at: "2026-10-17T18:00:00Z",
} as ScoreboardEntry;

describe("holding-period deadlines", () => {
  it("treats legacy naive timestamps as UTC", () => {
    expect(utcDate(entry.created_at).toISOString()).toBe("2026-10-10T18:00:00.000Z");
    expect(utcDate("2026-10-10T14:00:00-04:00").getTime()).toBe(utcDate(entry.created_at).getTime());
  });
  it("never shows a negative countdown or invents an outcome at the deadline", () => {
    expect(timeRemaining(entry.due_at!, utcDate(entry.created_at).getTime())).toBe("7d 0h 0m remaining");
    expect(timeRemaining(entry.due_at!, utcDate(entry.due_at!).getTime())).toContain("awaiting grading");
    expect(timeRemaining(entry.due_at!, utcDate(entry.due_at!).getTime() + 1000)).toContain("awaiting grading");
  });
  it("clamps progress before issue and after the deadline", () => {
    const start = utcDate(entry.created_at).getTime();
    const end = utcDate(entry.due_at!).getTime();
    expect(progressPercent(entry, start - 1000)).toBe(0);
    expect(progressPercent(entry, (start + end) / 2)).toBe(50);
    expect(progressPercent(entry, end + 1000)).toBe(100);
  });
});

it("keeps failed assessments separate from open predictions and missing outcome data", async () => {
  const { matchesOutcomeFilter, outcomeLabel } = await import("./trackRecord");
  const entries = ["hit", "miss", "in_progress", "awaiting_price", "unscored", "failed"].map(outcome => ({outcome}) as ScoreboardEntry);
  expect(entries.filter(e => matchesOutcomeFilter(e,"completed")).map(e=>e.outcome)).toEqual(["hit","miss"]);
  expect(entries.filter(e => matchesOutcomeFilter(e,"open")).map(e=>e.outcome)).toEqual(["in_progress","awaiting_price"]);
  expect(entries.filter(e => matchesOutcomeFilter(e,"unscored")).map(e=>e.outcome)).toEqual(["unscored"]);
  expect(entries.filter(e => matchesOutcomeFilter(e,"failed")).map(e=>e.outcome)).toEqual(["failed"]);
  expect(outcomeLabel.failed).toBe("Failed to assess");
});


it("keeps confidence unavailable for partial AI and rules-based predictions", async () => {
  const { confidenceLabel } = await import("./trackRecord");
  for (const prediction_kind of ["partial_ai","rules_based"] as const) {
    expect(confidenceLabel({recommendation:"Sell",confidence:80,analysis_status:"incomplete",prediction_kind} as ScoreboardEntry)).toBe("Confidence: Not assessed");
  }
  expect(confidenceLabel({recommendation:"Sell",confidence:80,prediction_kind:"ai",analysis_status:"complete"} as ScoreboardEntry)).toBe("80% confidence");
});
