import type { RuleCheck, Template } from "../api/practice";

export const starterIdeas = [
  {
    template: "breakout" as const,
    name: "A stock getting more attention",
    lesson:
      "Find a stock whose price has moved above its recent high, with more shares being bought and sold than usual.",
    why: "Someone might study this to see whether new interest keeps the price moving up. The price can also fall back.",
  },
  {
    template: "pullback" as const,
    name: "A pause in a rising stock",
    lesson:
      "Find a stock with a rising average price that is near its usual recent price and has just had an up day.",
    why: "Someone might study this instead of buying after a big jump. Being near an average does not make it cheap or safe.",
  },
  {
    template: "rsi_recovery" as const,
    name: "A stock starting to recover",
    lesson:
      "Look for early signs that a stock may be bouncing back after weak price moves. Its latest recorded price must also be higher than the day before.",
    why: "Someone might study this for early signs of a recovery. It can still keep falling.",
  },
];
export const ideaFor = (template: Template) =>
  starterIdeas.find((idea) => idea.template === template)!;

/** Older trade snapshots keep their saved checks; translate labels for display only. */
export function checkSummary(check: RuleCheck): string {
  if (check.summary) return check.summary;
  const old: Record<string, [string, string]> = {
    "Above prior highs": [
      "Its price finished above its recent high.",
      "Its price has not finished above its recent high.",
    ],
    "Extra volume": [
      "More shares changed hands than this search requires.",
      "Not enough extra shares changed hands to fit this search.",
    ],
    "Rising trend": [
      "Its longer-term average price is rising, and the recorded price is above it.",
      "Its price is not above a rising longer-term average.",
    ],
    "Near moving average": [
      "Its price is close to its recent average.",
      "Its price is too far from its recent average for this search.",
    ],
    "Up day": [
      "The price finished higher than the trading day before.",
      "The price did not finish higher than the trading day before.",
    ],
    "RSI crosses above threshold": [
      "A measure of price gains and losses has just moved back up past this search's recovery line.",
      "The price-change measure has not just moved back up past this search's recovery line.",
    ],
  };
  return old[check.label]?.[check.passed ? 0 : 1] ?? check.label;
}

export function friendlyPracticeError(error: unknown): string {
  const text = error instanceof Error ? error.message : "";
  if (/401|403/.test(text))
    return "Please sign in again so we can load your saved searches and pretend money.";
  if (/429/.test(text))
    return "We've checked a lot of prices recently. Wait about a minute, then try again.";
  if (/404/.test(text))
    return "That saved search or practice trade is no longer available. Reload this page to see your current ones.";
  if (/Failed to fetch|NetworkError|network|Load failed/i.test(text))
    return "We could not reach Verdict. Check your connection, then try again.";
  if (
    /Validation error|Input should|Field required|finite number|Value error/i.test(
      text,
    )
  )
    return "Check the form: use a name, a whole number of shares, and a short note. Your lower sell price must be below the buying price, and your higher sell price above it.";
  const plain = text
    .replace(/^\d{3}[^:]*:\s*/, "")
    .replace(/\s*\(request [^)]+\)$/, "");
  return plain && !/[{}<>]/.test(plain)
    ? plain
    : "Something did not load. Try again in a little while.";
}
