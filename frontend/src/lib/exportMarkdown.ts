import type { DebateCase, ResearchResponse } from "../api/client";

function caseSection(title: string, c: DebateCase | null): string {
  if (!c || c.status !== "ok") return "";
  const args = c.arguments
    .map((a) => `- ${a.claim}${a.evidence.length ? ` _[${a.evidence.join(", ")}]_` : ""}`)
    .join("\n");
  return `\n## ${title}\n\n> ${c.thesis}\n\n${args}\n`;
}

export function researchToMarkdown(
  result: ResearchResponse,
  meta: { duration_ms: number; cost_usd: number } | null,
): string {
  const { report, metrics, news, insider, evidence } = result;
  const lines: string[] = [
    `# Verdict — ${report.ticker}: ${report.recommendation}` +
      (report.confidence !== null ? ` (confidence ${report.confidence}/100)` : ""),
    "",
    `_Generated ${new Date().toISOString().slice(0, 10)} by Verdict. Not investment advice._`,
    "",
    report.justification,
  ];

  if (report.dissent) {
    lines.push("", "## Strongest opposing argument (overruled)", "", report.dissent);
  }
  if (report.falsifiers.length) {
    lines.push(
      "",
      "## What would change this verdict",
      "",
      ...report.falsifiers.map((f) => `- ${f}`),
    );
  }
  if (report.scores) {
    const s = report.scores;
    lines.push(
      "",
      "## Scorecard (0–10)",
      "",
      `| Valuation | Growth | Profitability | Balance sheet | Sentiment |`,
      `| --- | --- | --- | --- | --- |`,
      `| ${[s.valuation, s.growth, s.profitability, s.balance_sheet, s.sentiment]
        .map((v) => (v === null ? "–" : v))
        .join(" | ")} |`,
    );
  }

  lines.push(caseSection("Bull case", result.bull));
  lines.push(caseSection("Bear case", result.bear));

  if (report.company_overview) lines.push("", "## Company", "", report.company_overview);
  if (report.financial_health) lines.push("", "## Financial health", "", report.financial_health);
  if (report.key_risks.length) {
    lines.push("", "## Key risks", "", ...report.key_risks.map((r) => `- ${r}`));
  }
  if (news.summary) lines.push("", "## News", "", news.summary);
  if (insider.summary) lines.push("", "## Insider activity", "", insider.summary);
  if (report.delta_summary) lines.push("", "## Since the last run", "", report.delta_summary);

  const m: string[] = [];
  if (metrics.revenue !== null) m.push(`Revenue (TTM): $${(metrics.revenue / 1e9).toFixed(1)}B`);
  if (metrics.eps !== null) m.push(`EPS: ${metrics.eps.toFixed(2)}`);
  if (metrics.pe_ratio !== null) m.push(`P/E: ${metrics.pe_ratio.toFixed(1)}`);
  if (metrics.profit_margin !== null) m.push(`Margin: ${(metrics.profit_margin * 100).toFixed(1)}%`);
  if (metrics.current_price !== null) m.push(`Price at run: $${metrics.current_price.toFixed(2)}`);
  if (m.length) lines.push("", "## Metrics", "", ...m.map((x) => `- ${x}`));

  if (evidence.length) {
    lines.push(
      "",
      "## Appendix — evidence ledger",
      "",
      ...evidence.map((e) => `- \`${e.id}\` **${e.label}** — ${e.content}${e.url ? ` ([source](${e.url}))` : ""}`),
    );
  }
  if (meta) {
    lines.push("", `---`, `_Run: ${(meta.duration_ms / 1000).toFixed(1)}s · $${meta.cost_usd.toFixed(4)}_`);
  }
  return lines.filter((l) => l !== undefined).join("\n");
}

export function downloadReportMarkdown(
  result: ResearchResponse,
  meta: { duration_ms: number; cost_usd: number } | null,
): void {
  const md = researchToMarkdown(result, meta);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `verdict-${result.ticker.toLowerCase()}-${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}
