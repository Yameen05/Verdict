import { failedAssessment, predictionKind } from "./assessment";
import type { StreamEvent } from "../api/client";

// Fixed work weights keep parallel completions and optional reflection monotonic.
const weights: Record<string, number> = {
  filing0: 2, filing1: 2, filing2: 2, filing3: 2,
  news: 2, metrics: 2, insider: 1, signals: 1, bull: 2, bear: 2,
  review: 1, report: 1,
};
export interface ProgressState {
  completed: string[];
  waits: Record<string, "queue" | "capacity">;
  phase: "active" | "complete" | "partial" | "error" | "cancelled" | "cached";
  label: string;
}
export const initialProgress = (): ProgressState => ({ completed: [], waits: {}, phase: "active", label: "Gathering company information" });
export function progressPercent(state: ProgressState): number {
  const value = state.completed.reduce((sum, key) => sum + (weights[key] ?? 0), 0) * 5;
  return state.phase === "complete" ? 100 : Math.min(value, 95);
}
export function stopProgress(state: ProgressState, phase: "error" | "cancelled"): ProgressState {
  return { ...state, phase, waits: {}, label: phase === "cancelled" ? "Research cancelled" : "Research could not finish" };
}
export function advanceProgress(state: ProgressState, event: StreamEvent): ProgressState {
  if (state.phase !== "active") return state;
  let next = { ...state, completed: [...state.completed], waits: { ...state.waits } };
  const credit = (...keys: string[]) => { next.completed = [...new Set([...next.completed, ...keys])]; };
  if (event.event === "progress") {
    const data = event.data;
    if (data.kind === "filing_question" && Number.isInteger(data.index) && data.index >= 0 && data.index < 4) credit(`filing${data.index}`);
    if (data.kind === "provider_wait") {
      if (data.phase === "started") next.waits[data.id] = data.reason;
      else delete next.waits[data.id];
    }
  } else if (event.event === "ingest") {
    next.label = event.data.phase === "started" ? "Getting the company filing" : "Checking filings, news, and numbers";
  } else if (event.event === "node_completed") {
    const { node, payload } = event.data;
    const slot = node.replace(/_agent$/, "");
    const result = payload[slot] as { status?: string; failure?: unknown; error?: string; findings?: {source_chunks: number}[] } | undefined;
    if (node === "sec_agent" && result?.status === "ok") credit("filing0", "filing1", "filing2", "filing3");
    // Crypto filings are intentionally inapplicable, rather than a failed check.
    if (["sec_agent", "insider_agent"].includes(node) && result?.status === "skipped" && /crypto/i.test(result.error ?? "")) {
      if (node === "sec_agent") credit("filing0", "filing1", "filing2", "filing3");
      else credit("insider");
    }
    if (["insider", "signals"].includes(slot) && result?.status === "skipped" && !result.failure) credit(slot);
    if (["news", "metrics", "insider", "signals", "bull", "bear"].includes(slot) && result?.status === "ok" && !result.failure) credit(slot);
    if (node === "build_evidence") next.label = "Weighing the positive and negative cases";
    if (node === "judge") {
      next.label = payload.followup_question ? "Checking an extra filing question" : "Preparing the report";
      const report = payload.report as { degraded?: boolean; recommendation?: string; failures?: {stage?: string}[] } | undefined;
      if (report && !["Pending", "Failed"].includes(report.recommendation ?? "") && !report.failures?.some(f => f.stage === "final review")) credit("review");
    }
  } else if (event.event === "debate") {
    const data = event.data;
    if (data.kind === "debate_case" && data.case.status === "ok") credit(data.stance);
    if (data.kind === "judge_phase") next.label = data.phase === "followup" ? "Checking an extra filing question" : "Writing the final review";
  } else if (event.event === "completed") {
    next.waits = {};
    if (event.data.cached) return { ...next, phase: "cached", label: "Loaded a saved report" };
    const result = event.data.result;
    const failed = failedAssessment(result);
    // A terminal snapshot can fill in missed events, but only for successful steps.
    for (const [key, data] of Object.entries(result)) {
      if (data && typeof data === "object" && "status" in data && data.status === "ok" && !("failure" in data && data.failure)) {
        if (key === "sec") credit("filing0", "filing1", "filing2", "filing3");
        else if (key in weights) credit(key);
      } else if ((key === "insider" || key === "signals") && data && typeof data === "object" && "status" in data && data.status === "skipped" && !("failure" in data && data.failure)) {
        credit(key);
      } else if ((key === "sec" || key === "insider") && data && typeof data === "object" && "status" in data && data.status === "skipped" && "error" in data && /crypto/i.test(String(data.error))) {
        if (key === "sec") credit("filing0", "filing1", "filing2", "filing3");
        else credit("insider");
      }
    }
    if (!failed) credit("review", "report");
    const full = !failed && Object.keys(weights).every(key => next.completed.includes(key));
    next.phase = full ? "complete" : "partial";
    next.label = full ? "Research complete" : predictionKind(result) !== "none" ? "Analysis incomplete — original prediction recorded" : "Failed to assess — some checks could not finish";
  } else if (event.event === "error") return stopProgress(next, "error");
  return next;
}
