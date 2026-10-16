import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ResearchResponse } from "../api/client";
import { VerdictCard } from "../components/VerdictCard";
import { CalibrationPanel } from "../components/CalibrationPanel";
import { CONFIDENCE_EXPLANATION } from "./confidence";
import { researchToMarkdown } from "./exportMarkdown";
import { LEGAL_DOCS } from "./legal";

function fixture(): ResearchResponse {
  return { ticker:"AAPL", sec:{status:"ok",findings:[]}, news:{status:"ok",article_count:0,summary:null},
    metrics:{status:"ok",current_price:100,revenue:null,eps:null,pe_ratio:null,profit_margin:null},
    insider:{status:"ok",summary:null}, signals:{status:"ok",sources_used:[]}, bull:null,bear:null,evidence:[],
    report:{ticker:"AAPL",recommendation:"Buy",confidence:82,degraded:false,justification:"General stock evidence",
      horizon_days:14,key_risks:[],falsifiers:[],company_overview:"",financial_health:""},
  } as unknown as ResearchResponse;
}

describe("score presentation and authentic records", () => {
  it("renders the original Buy and score with an adjacent odds explanation", () => {
    const raw = fixture(); const snapshot = JSON.stringify(raw);
    const html = renderToStaticMarkup(createElement(VerdictCard, {result:raw,meta:null,onExport:()=>undefined}));
    expect(html).toContain("Buy");
    expect(html).toContain("AI assessment score 82 out of 100");
    expect(html).toContain("not verified odds of profit");
    expect(JSON.stringify(raw)).toBe(snapshot);
  });
  it("exports the same prediction with explicit score meaning", () => {
    const raw = fixture();
    const markdown = researchToMarkdown(raw,null);
    expect(markdown).toContain("AAPL: Buy (AI assessment score 82/100)");
    expect(markdown).toContain(CONFIDENCE_EXPLANATION);
    expect(markdown).toContain("Hold is not a validated 50/50");
    expect(raw.report.confidence).toBe(82);
  });
  it("does not claim that historical diagnostics validate profit odds", () => {
    const html = renderToStaticMarkup(createElement(CalibrationPanel,{report:fixture(),refreshKey:0}));
    expect(html).toContain("not verified odds of profit");
    expect(html).toContain("grading rule");
    expect(html).not.toContain("perfectly calibrated");
  });
});

it("privacy copy describes free text and avoids an unimplemented deletion promise", () => {
  const privacy = LEGAL_DOCS.find(d=>d.id === "privacy")!;
  const copy = privacy.sections.flatMap(s=>s.body).join(" ");
  expect(copy).toContain("free-text question, recent conversation history");
  expect(copy).toContain("Personal details you type");
  expect(copy).toContain("no self-service account deletion");
  expect(copy).toContain("Shared research, security records, backups");
  expect(copy).not.toContain("never your password or personal details");
  expect(copy).not.toContain("deletion removes your account");
});

import { SignupAgreement } from "../components/SignupAgreement";
import { authApi, explicitLegalAcceptance, legalDocumentsCurrent } from "../api/auth";
import legalManifest from "./legalManifest.json";
import { vi } from "vitest";

it("presents compact linked documents and an unchecked, associated agreement control", () => {
  const html = renderToStaticMarkup(createElement(SignupAgreement,{checked:false,onChange:()=>undefined,current:true}));
  expect(html).toContain("Terms of Service");
  expect(html).toContain("Risk Disclosure");
  expect(html).not.toContain("What leaves the server");
  expect(html).not.toContain("<details");
  expect(html).toContain('for="signup-agreement"');
  expect(html).toContain("AI research can be wrong");
  expect(html).toContain("liability limits apply only as law permits");
  expect(html).toContain('type="checkbox"');
  expect(html).not.toContain('checked=""');
  expect(html).toContain("No marketing or unrelated data-use consent");
});

it("blocks stale-document acceptance and compares every version plus the content fingerprint", () => {
  expect(legalDocumentsCurrent(legalManifest)).toBe(true);
  expect(legalDocumentsCurrent(undefined)).toBe(false);
  for (const key of ["terms","risk","privacy"] as const) {
    expect(legalDocumentsCurrent({...legalManifest,versions:{...legalManifest.versions,[key]:"old"}})).toBe(false);
  }
  expect(legalDocumentsCurrent({...legalManifest,content_sha256:"old"})).toBe(false);
  const html = renderToStaticMarkup(createElement(SignupAgreement,{checked:false,onChange:()=>undefined,current:false}));
  expect(html).toContain("Refresh the app");
  expect(html).toMatch(/type="checkbox"[^>]*disabled/);
});

it("sends account agreement only after explicit acceptance, and leaves ordinary login alone", async () => {
  const bodies: Record<string,unknown>[] = [];
  vi.stubGlobal("fetch", vi.fn(async (_url, init: RequestInit) => {
    bodies.push(JSON.parse(init.body as string));
    return new Response(JSON.stringify({user:{id:1,email:"test@example.com",role:"member"},csrf_token:"synthetic"}),{status:200});
  }));
  try {
    await authApi.register("","test@example.com","A-long-password-123",false);
    await authApi.googleLogin("synthetic", "");
    await authApi.login("test@example.com","A-long-password-123");
    for (const body of bodies) expect(body).not.toHaveProperty("legal_acceptance");
    await authApi.register("","test@example.com","A-long-password-123",true);
    await authApi.bootstrap("test@example.com","A-long-password-123","synthetic",true);
    await authApi.googleLogin("synthetic","",true);
    for (const body of bodies.slice(3)) expect(body.legal_acceptance).toEqual(explicitLegalAcceptance());
  } finally { vi.unstubAllGlobals(); }
});
