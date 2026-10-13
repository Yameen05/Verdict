import { describe, expect, it } from "vitest";
import { practiceSize } from "./practiceMath";

describe("practice sizing", () => {
  it("limits both stop risk and available cash", () => {
    expect(practiceSize(100000, 100, 95, 1)).toBe(200);
    expect(practiceSize(1000, 100, 99, 10)).toBe(10);
    expect(practiceSize(50, 100, 95, 1)).toBe(0);
  });
  it("uses cent precision and whole shares", () => {
    expect(practiceSize(1000, 33.33, 32.33, 1)).toBe(10);
    expect(practiceSize(99.99, 33.33, 32.33, 100)).toBe(3);
  });
  it("rejects invalid stop and budget inputs", () => {
    for (const [cash, entry, stop, risk] of [
      [NaN, 100, 95, 1],
      [100, 100, 100, 1],
      [100, 100, -1, 1],
      [100, 100, 95, Infinity],
      [100, 100, 95, 101],
    ]) {
      expect(practiceSize(cash, entry, stop, risk)).toBe(0);
    }
  });
});
