import { describe, expect, it } from "vitest";
import type { ResearchResponse } from "../api/client";
import { failedAssessment, normalizeResearch } from "./assessment";
import { researchToMarkdown } from "./exportMarkdown";
function fixture(): ResearchResponse {
  return {ticker:"AAPL",sec:{status:"ok",findings:[]},news:{status:"ok",article_count:0,summary:null},metrics:{status:"ok",current_price:100,revenue:null,eps:null,pe_ratio:null,profit_margin:null},insider:{status:"ok",summary:null},signals:{status:"ok",sources_used:[]},bull:null,bear:null,evidence:[],report:{ticker:"AAPL",recommendation:"Hold",confidence:50,degraded:false,justification:"Mixed signals",horizon_days:14,key_risks:[],falsifiers:[],company_overview:"",financial_health:""}} as unknown as ResearchResponse;
}
describe("failed assessment display and export", () => {
  it("projects old HOLD/50 degraded reports without changing stored input", () => {
    const raw = fixture(); raw.report.degraded = true;
    const safe = normalizeResearch(raw);
    expect(safe.report.recommendation).toBe("Failed");expect(safe.report.confidence).toBeNull();
    expect(raw.report.recommendation).toBe("Hold");expect(raw.report.confidence).toBe(50);
    const markdown = researchToMarkdown(raw,null);
    expect(markdown).toContain("Confidence: Failed to assess");
    expect(markdown).not.toContain("confidence 50");
    expect(markdown).not.toContain("AAPL: Hold");
  });
  it("preserves an issued prediction with warning when a source failed", () => {
    const raw = fixture();raw.sec.status = "error";raw.sec.error = "503 PRIVATE secret";
    const safe = normalizeResearch(raw);
    expect(safe.report.analysis_warning).toContain("filing review");
    expect(safe.report.analysis_warning).toContain("temporarily busy");
    expect(safe.report.analysis_warning).not.toContain("PRIVATE");
    expect(safe.report.confidence).toBeNull();
    expect(safe.report.recommendation).toBe("Hold");
    expect(safe.report.prediction_kind).toBe("partial_ai");
  });
  it("retains complete reports with unknown news coverage and optional absence", () => {
    const raw = fixture();raw.insider.status = "skipped";
    expect(failedAssessment(raw)).toBe(false);expect(normalizeResearch(raw)).toBe(raw);
    expect(raw.report.confidence).toBe(50);
  });
});


it("exports restored Sell predictions with partial warnings and no numeric confidence", () => {
  const raw = fixture();raw.report.recommendation = "Sell";raw.report.confidence = 80;
  raw.sec.status = "error";raw.sec.error = "401 PRIVATE";
  const md = researchToMarkdown(raw,null);
  expect(md).toContain("AAPL: Sell");
  expect(md).toContain("Confidence: Not assessed — analysis incomplete");
  expect(md).toContain("partial_ai");expect(md).not.toContain("confidence 80");
  expect(md).not.toContain("PRIVATE");
});
