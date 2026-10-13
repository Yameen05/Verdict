/** Whole-share, cash-only sizing. Planned stop risk does not cap gap losses. */
export function practiceSize(
  cash: number,
  entry: number,
  stop: number,
  riskPct: number,
): number {
  if (
    ![cash, entry, stop, riskPct].every(Number.isFinite) ||
    cash <= 0 ||
    entry <= stop ||
    stop <= 0 ||
    riskPct <= 0 ||
    riskPct > 100
  )
    return 0;
  const entryCents = Math.round(entry * 100);
  const riskCents = entryCents - Math.round(stop * 100);
  if (riskCents <= 0) return 0;
  return Math.max(
    0,
    Math.min(
      Math.floor(Math.round(cash * 100) / entryCents),
      Math.floor((cash * riskPct) / riskCents),
    ),
  );
}
