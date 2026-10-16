import { describe, expect, it } from "vitest";
import { safeExternalUrl } from "./safeUrl";

describe("external evidence links", () => {
  it.each(["javascript:alert(1)", "data:text/html,hi", "file:///etc/passwd", "//evil.example", "https://user:pass@example.com", "broken"])("rejects %s", (url) => {
    expect(safeExternalUrl(url)).toBeUndefined();
  });
  it("keeps a normal source URL", () => {
    expect(safeExternalUrl("https://www.sec.gov/Archives/test?q=1")).toBe("https://www.sec.gov/Archives/test?q=1");
  });
});
