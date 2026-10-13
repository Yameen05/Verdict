import type { ResearchResponse } from "../api/client";
import { researchError } from "./researchErrors";

export function failedAssessment(result: ResearchResponse): boolean {
  const report = result.report;
  return Boolean(report.degraded || report.failures?.length || report.recommendation === "Failed" || report.recommendation === "Pending" ||
    (report.assessment_status && report.assessment_status !== "complete") ||
    (Boolean(result.bull || result.bear) && (!result.bull || !result.bear)) ||
    [result.sec, result.news, result.metrics, result.bull, result.bear].some(source => source?.status === "error" || source?.failure) ||
    /full AI analysis could not run|full AI analysis was unavailable|limited verdict from the data already collected/i.test(report.justification ?? ""));
}

export function predictionKind(result: ResearchResponse): "ai" | "partial_ai" | "rules_based" | "none" {
  const r = result.report;
  if (!["Buy", "Hold", "Sell"].includes(r.recommendation) || r.prediction_kind === "none") return "none";
  const fallback = /conservative fallback verdict|AI judge was unavailable|full AI analysis could not run|full AI analysis was unavailable|limited verdict from the data already collected/i.test(r.justification ?? "");
  const kind = r.prediction_kind ?? (fallback || r.degraded ? "rules_based" : failedAssessment(result) ? "partial_ai" : "ai");
  if(kind === "rules_based" && r.recommendation === "Hold" && r.confidence === 50) return "none";
  return kind === "ai" && failedAssessment(result) ? "partial_ai" : kind;
}

/** Display/export projection; the original saved record remains intact. */
export function normalizeResearch(result: ResearchResponse): ResearchResponse {
  if (!failedAssessment(result)) return result;
  const stages = [
    ["filing review", result.sec], ["news review", result.news], ["financial review", result.metrics],
    ["insider review", result.insider], ["market signals", result.signals], ["positive case", result.bull], ["negative case", result.bear],
  ] as const;
  const failures = result.report.failures ?? [];
  const causes = failures.map(f => `${f.stage ?? "AI review"}: ${researchError(f)}`);
  for (const [label, source] of stages) {
    if (source?.status === "error" || source?.failure) {
      if (!failures.some(f => f.stage === source.failure?.stage)) causes.push(`${label}: ${researchError(source.failure ?? new Error(source.error ?? ""))}`);
    }
  }
  const reason = [...new Set(causes)].join(" ") || "A required research step could not finish. Its exact cause was not recorded.";
  const kind = predictionKind(result);
  const issued = kind !== "none";
  const warning = `Analysis incomplete. ${reason} The originally issued prediction remains tracked; confidence was not assessed.`;
  const justification = `Failed to assess. ${reason} Collected facts are incomplete and do not form a scored recommendation.`;
  return { ...result, report: { ...result.report, recommendation:issued ? result.report.recommendation : "Failed", confidence:null, scores:null,
    prediction_kind:kind, analysis_warning:issued ? warning : reason,
    assessment_status:issued ? "incomplete" : "failed", degraded:true,
    justification:issued ? result.report.justification : justification, simple_summary:issued ? result.report.simple_summary : justification, dissent:null, delta_summary:null, horizon_outlook:null } };
}
