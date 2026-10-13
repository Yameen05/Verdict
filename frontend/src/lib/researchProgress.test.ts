import { describe, expect, it } from "vitest";
import type { StreamEvent, ResearchResponse } from "../api/client";
import { advanceProgress, initialProgress, progressPercent, stopProgress } from "./researchProgress";
const node = (node: string, payload: Record<string, unknown>): StreamEvent => ({event:"node_completed",data:{node,payload}});
const question = (index: number): StreamEvent => ({event:"progress", data:{kind:"filing_question",index}});
const wait = (id: string, reason: "queue" | "capacity", phase: "started" | "done"): StreamEvent => ({event:"progress",data:{kind:"provider_wait",id,reason,phase}});
const result = (degraded=false): ResearchResponse => ({sec:{status:"ok"},news:{status:"ok"},metrics:{status:"ok"},insider:{status:"ok"},signals:{status:"ok"},bull:{status:"ok"},bear:{status:"ok"},report:{degraded,recommendation:"Hold"}} as ResearchResponse);
const end = (degraded=false,cached=false): StreamEvent => ({event:"completed", data:{result:result(degraded),cached,request_id:"fixture",duration_ms:0,cost:{},persisted_id:null}});
describe("event-based research progress", () => {
  it("deduplicates parallel filing completions and ignores starts/waits", () => {
    let p = initialProgress();
    p = advanceProgress(p, question(2));
    expect(progressPercent(p)).toBe(10);
    p = advanceProgress(p, question(2));
    p = advanceProgress(p, wait("a","queue","started"));
    p = advanceProgress(p, wait("b","capacity","started"));
    expect(progressPercent(p)).toBe(10);
    p = advanceProgress(p, wait("a","queue","done"));
    expect(p.waits).toEqual({b:"capacity"});
  });
  it("never jumps backwards or reaches 100 for optional reflection or partial results", () => {
    let p = initialProgress();
    const percentages = [progressPercent(p)];
    for (const event of [question(3),node("metrics_agent",{metrics:{status:"ok"}}),question(0),node("judge",{followup_question:"More evidence?"}),node("followup",{}),end(true)]) {
      p = advanceProgress(p,event); percentages.push(progressPercent(p));
    }
    expect(percentages).toEqual([...percentages].sort((a,b)=>a-b));
    expect(p.phase).toBe("partial"); expect(progressPercent(p)).toBeLessThan(100);
  });
  it("counts actual work and reaches 100 only for a complete fresh report", () => {
    let p = advanceProgress(initialProgress(),end());
    expect(p.phase).toBe("complete");expect(progressPercent(p)).toBe(100);
    p = advanceProgress(p,wait("late","queue","started"));
    expect(p.waits).toEqual({});
  });
  it("failed steps do not advance and early termination preserves completed work", () => {
    const p = advanceProgress(advanceProgress(initialProgress(),question(1)),node("bull_agent",{bull:{status:"error"}}));
    expect(progressPercent(p)).toBe(10);
    for(const phase of ["cancelled","error"] as const) {
      const stopped = stopProgress(p,phase);
      expect(progressPercent(stopped)).toBe(10);
      expect(advanceProgress(stopped,end()).phase).toBe(phase);
      expect(stopped.waits).toEqual({});
    }
    expect(progressPercent(initialProgress())).toBe(0);
  });
  it("cached runs do not pretend to perform fresh work", () => {
    const p = advanceProgress(initialProgress(),end(false,true));
    expect(p.phase).toBe("cached"); expect(p.completed).toEqual([]);
  });
});

it("finishes successful reports when optional checks are intentionally skipped", () => {
  const event = end();
  if(event.event !== "completed") throw new Error("fixture");
  event.data.result.insider.status = "skipped";
  event.data.result.signals.status = "skipped";
  const p = advanceProgress(initialProgress(),event);
  expect(p.phase).toBe("complete");expect(progressPercent(p)).toBe(100);
});
