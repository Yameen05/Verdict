import { describe, it, expect } from "vitest";
import { researchError } from "./researchErrors";
import { errorFromResponse } from "../api/http";

describe("honest public AI errors", () => {
  it.each([
    ["429 raw secret", "did not identify"],
    ["503 raw secret", "temporarily busy"],
    ["APIConnectionError raw secret", "could not reach"],
    ["TimeoutError raw secret", "timed out"],
    ["401 raw secret", "configuration"],
    ["quota raw secret", "short wait may not help"],
    ["You've used 100 fresh runs, midnight UTC raw secret", "Verdict's daily"],
    ["arbitrary raw secret", "could not finish"],
  ])("sanitizes %s", (raw, expected) => {
    expect(researchError(new Error(raw))).toContain(expected);
    expect(researchError(new Error(raw))).not.toContain("secret");
  });
  it("preserves structured categories through HTTP, ahead of 429", async () => {
    const error = await errorFromResponse(new Response(JSON.stringify({detail: {kind:"provider_daily_limit", message:"secret"}}), {status:429}));
    expect(researchError(error)).toContain("daily AI quota");
    expect(researchError(error)).not.toContain("secret");
  });
  it("never treats daily/token quota as a short RPM wait", () => {
    for (const kind of ["provider_daily_limit", "provider_token_limit"]) {
      const message = researchError({failure:{kind, window:"day", message:"secret", retry_after_seconds:5}});
      expect(message).toContain("shortly");
      expect(message).not.toContain("5 seconds");
    }
  });
  it("uses a supplied minute retry delay without inventing resets", () => {
    const text = researchError({failure:{kind:"provider_rate_limit",retry_after_seconds:13}});
    expect(text).toContain("13 seconds");
    expect(text).not.toContain("midnight");
  });
});
