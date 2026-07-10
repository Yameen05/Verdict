import type { ResearchResponse, TimingAssessment } from "../api/client";

export interface Disagreement {
  title: string;
  body: string;
  severity: "watch" | "important";
}

export function verdictLean(rec: string): number {
  if (rec === "Buy") return 1;
  if (rec === "Sell") return -1;
  return 0;
}

export function timingLean(action: TimingAssessment["action"] | undefined): number {
  if (action === "buy_now" || action === "accumulate") return 1;
  if (action === "avoid") return -1;
  return 0;
}

export function buildDisagreements(
  research: ResearchResponse | null,
  timing: TimingAssessment | null,
): Disagreement[] {
  if (!research) return [];
  const out: Disagreement[] = [];
  const rec = research.report.recommendation;
  const recLean = verdictLean(rec);

  const analyst = research.signals.analyst;
  if (analyst && Math.abs(analyst.score) >= 0.15 && recLean !== 0) {
    const analystLean = analyst.score > 0 ? 1 : -1;
    if (analystLean !== recLean) {
      out.push({
        title: "Analysts disagree with the verdict",
        body: `Analyst consensus is ${analyst.consensus}, but the report says ${rec}. That means other evidence outweighed Wall Street ratings.`,
        severity: "important",
      });
    }
  }

  const retail = research.signals.retail;
  if (retail && retail.sample >= 5 && Math.abs(retail.score) >= 0.25 && recLean !== 0) {
    const retailLean = retail.score > 0 ? 1 : -1;
    if (retailLean !== recLean) {
      out.push({
        title: "Retail sentiment disagrees",
        body: `Retail chatter is ${retail.label}, but the report says ${rec}. Retail sentiment can be noisy, so it should not override stronger evidence by itself.`,
        severity: "watch",
      });
    }
  }

  const timingScore = timingLean(timing?.action);
  if (timing && timingScore !== 0 && recLean !== 0 && timingScore !== recLean) {
    out.push({
      title: "Timing and verdict disagree",
      body: `The full report says ${rec}, while timing says ${timing.action_label}. This usually means the longer thesis and the current entry price are not saying the same thing.`,
      severity: "important",
    });
  }

  if (timing?.action === "wait_pullback" && rec === "Buy") {
    out.push({
      title: "Bullish, but not at any price",
      body: "The app likes the stock more than the current entry. Holding may be fine, but new money should wait for a better price.",
      severity: "watch",
    });
  }

  if (research.signals.macro?.regime === "restrictive" && rec === "Buy") {
    out.push({
      title: "Macro is a headwind",
      body: "The stock-specific case won, but the macro backdrop is restrictive. That can make upside choppier and drawdowns sharper.",
      severity: "watch",
    });
  }

  if (research.signals.earnings_days !== null && research.signals.earnings_days <= 7 && rec === "Buy") {
    out.push({
      title: "Earnings are close",
      body: `Earnings are in about ${research.signals.earnings_days} day(s). Even a good setup can gap down on earnings, so position size matters.`,
      severity: "important",
    });
  }

  return out.slice(0, 4);
}
