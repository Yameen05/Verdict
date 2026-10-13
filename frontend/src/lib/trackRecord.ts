import type { ScoreboardEntry } from "../api/types";

export function utcDate(iso: string): Date {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

export function dateTime(iso: string): string {
  return utcDate(iso).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "numeric",
    minute: "2-digit", second: "2-digit", timeZoneName: "short",
  });
}

export function timeRemaining(due: string, now: number): string {
  const seconds = Math.max(0, Math.ceil((utcDate(due).getTime() - now) / 1000));
  if (!seconds) return "Holding period ended · awaiting grading";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days ? `${days}d ` : ""}${hours}h ${minutes}m remaining`;
}

export function progressPercent(entry: ScoreboardEntry, now: number): number {
  const start = utcDate(entry.created_at).getTime();
  if (!entry.due_at) return 0;
  const end = utcDate(entry.due_at).getTime();
  return Math.max(0, Math.min(100, ((now - start) / (end - start)) * 100));
}

export const outcomeLabel: Record<ScoreboardEntry["outcome"], string> = {
  hit: "Hit", miss: "Miss", in_progress: "In progress",
  awaiting_price: "Awaiting price", unscored: "Unscored", failed: "Failed to assess",
};

export function money(value: number | null): string {
  return value === null ? "—" : value.toLocaleString(undefined, {
    style: "currency", currency: "USD", maximumFractionDigits: 4,
  });
}

export function returnLabel(value: number | null): string {
  return value === null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}


export type OutcomeFilter = "completed" | "open" | "unscored" | "failed";

export function matchesOutcomeFilter(entry: ScoreboardEntry, filter: OutcomeFilter): boolean {
  if (filter === "completed") return entry.outcome === "hit" || entry.outcome === "miss";
  if (filter === "open") return entry.outcome === "in_progress" || entry.outcome === "awaiting_price";
  return entry.outcome === filter;
}


export const predictionTypeLabel = { ai:"Complete AI", partial_ai:"Partial AI", rules_based:"Rules-based", none:"No issued prediction" };
export function confidenceLabel(entry: ScoreboardEntry): string {
  if (entry.recommendation === "Failed") return "Confidence: Failed to assess";
  if (entry.analysis_status === "incomplete" || entry.prediction_kind === "partial_ai" || entry.prediction_kind === "rules_based") return "Confidence: Not assessed";
  return entry.confidence === null ? "Confidence not recorded" : `${entry.confidence}% confidence`;
}
