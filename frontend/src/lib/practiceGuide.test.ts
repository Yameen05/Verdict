import { describe, expect, it } from "vitest";
import { checkSummary, friendlyPracticeError } from "./practiceGuide";

describe("existing practice history", () => {
  it("explains old checks without changing saved facts", () => {
    const old = Object.freeze({
      label: "RSI crosses above threshold",
      passed: true,
      explanation: "RSI(14) 25 → 35; threshold 30",
    });
    expect(checkSummary(old)).toContain("price gains and losses");
    expect(old.explanation).toBe("RSI(14) 25 → 35; threshold 30");
    expect(checkSummary({ ...old, passed: false })).toContain("has not");
  });
  it("uses server explanations when available", () => {
    expect(
      checkSummary({
        label: "Condition",
        passed: true,
        explanation: "numbers",
        summary: "The price finished higher.",
      }),
    ).toBe("The price finished higher.");
  });
});
describe("practice errors", () => {
  it("gives a useful next action for sign-in, throttling and lost connections", () => {
    expect(
      friendlyPracticeError(new Error("403 Forbidden: CSRF validation failed")),
    ).toContain("sign in again");
    expect(friendlyPracticeError(new Error("429 Too Many Requests"))).toContain(
      "minute",
    );
    expect(friendlyPracticeError(new TypeError("Failed to fetch"))).toContain(
      "connection",
    );
  });
  it("keeps useful server feedback while removing HTTP and request-id clutter", () => {
    expect(
      friendlyPracticeError(
        new Error("409 Conflict: Try fewer shares (request abc-123)"),
      ),
    ).toBe("Try fewer shares");
    expect(
      friendlyPracticeError(
        new Error("422 Unprocessable Entity: Validation error"),
      ),
    ).toContain("whole number of shares");
    expect(
      friendlyPracticeError(
        new Error("500 Internal Server Error: <html>error</html>"),
      ),
    ).not.toContain("html");
  });
});
