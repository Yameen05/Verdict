import type { ResearchResponse } from "../api/client";

interface Props {
  result: ResearchResponse | null;
}

const statusColors: Record<string, string> = {
  ok: "text-emerald-400",
  skipped: "text-amber-400",
  not_implemented: "text-slate-500",
  error: "text-rose-400",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs uppercase tracking-wide ${statusColors[status] ?? "text-slate-400"}`}>
      {status}
    </span>
  );
}

/** Per-source findings: what each fetch agent actually brought back. */
export function ReportPanel({ result }: Props) {
  if (!result) return null;
  const { report, sec, news, metrics, insider, signals } = result;

  return (
    <section className="mt-6 space-y-4">
      {(report.company_overview || report.financial_health || report.key_risks.length > 0) && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <div className="grid gap-4 md:grid-cols-3">
            {report.company_overview && (
              <Section title="Company overview">{report.company_overview}</Section>
            )}
            {report.financial_health && (
              <Section title="Financial health">{report.financial_health}</Section>
            )}
            {report.key_risks.length > 0 && (
              <div>
                <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">
                  Key risks
                </h3>
                <ul className="list-inside list-disc space-y-1 text-sm text-slate-200">
                  {report.key_risks.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <AgentCard title="SEC filings" status={sec.status} error={sec.error}>
          {sec.findings.length > 0 && (
            <ul className="space-y-2 text-xs text-slate-300">
              {sec.findings.map((f, i) => (
                <li key={i}>
                  <div className="font-medium text-slate-200">{f.question}</div>
                  <div className="text-slate-400">{f.answer}</div>
                </li>
              ))}
            </ul>
          )}
          {sec.accession && (
            <div className="mt-2 text-[10px] text-slate-500">accession {sec.accession}</div>
          )}
        </AgentCard>

        <AgentCard title="News & sentiment" status={news.status} error={news.error}>
          {news.summary && <p className="text-xs text-slate-300">{news.summary}</p>}
          {news.sentiment_score !== null && (
            <p className="mt-1 text-xs text-slate-400">
              aggregate score {news.sentiment_score.toFixed(2)} · {news.article_count} articles
            </p>
          )}
          {news.top_headlines.length > 0 && (
            <ul className="mt-2 space-y-1.5 border-t border-slate-800 pt-2 text-[11px]">
              {news.top_headlines.slice(0, 5).map((h, i) => (
                <li key={i} className="flex items-baseline gap-1.5">
                  <span
                    className={`shrink-0 font-mono text-[9px] ${
                      h.score === null
                        ? "text-slate-600"
                        : h.score > 0.05
                        ? "text-emerald-400"
                        : h.score < -0.05
                        ? "text-rose-400"
                        : "text-slate-500"
                    }`}
                  >
                    {h.score === null ? "·" : (h.score > 0 ? "+" : "") + h.score.toFixed(1)}
                  </span>
                  {h.url ? (
                    <a
                      href={h.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-slate-300 hover:text-indigo-300 hover:underline"
                    >
                      {h.title}
                    </a>
                  ) : (
                    <span className="text-slate-300">{h.title}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </AgentCard>

        <AgentCard title="Financial metrics" status={metrics.status} error={metrics.error}>
          {metrics.current_price !== null && (
            <Metric label="Price" value={`$${metrics.current_price.toFixed(2)}`} />
          )}
          {metrics.revenue !== null && (
            <Metric label="Revenue (TTM)" value={`$${(metrics.revenue / 1e9).toFixed(1)}B`} />
          )}
          {metrics.eps !== null && <Metric label="EPS (TTM)" value={metrics.eps.toFixed(2)} />}
          {metrics.pe_ratio !== null && <Metric label="P/E" value={metrics.pe_ratio.toFixed(1)} />}
          {metrics.profit_margin !== null && (
            <Metric label="Profit margin" value={`${(metrics.profit_margin * 100).toFixed(1)}%`} />
          )}
          {metrics.debt_to_equity !== null && (
            <Metric label="Debt / equity" value={metrics.debt_to_equity.toFixed(1)} />
          )}
          {metrics.week_52_low !== null && metrics.week_52_high !== null && (
            <Metric
              label="Year range (52 weeks)"
              value={`$${metrics.week_52_low.toFixed(2)} – $${metrics.week_52_high.toFixed(2)}`}
            />
          )}
          {metrics.recent_return_pct !== null && (
            <Metric
              label="Recent move (your window)"
              value={`${metrics.recent_return_pct > 0 ? "+" : ""}${metrics.recent_return_pct.toFixed(1)}%`}
            />
          )}
          {metrics.typical_swing_pct !== null && (
            <Metric
              label="Typical swing (your window)"
              value={`±${metrics.typical_swing_pct.toFixed(1)}%`}
            />
          )}
        </AgentCard>

        <AgentCard title="Insider activity" status={insider.status} error={insider.error}>
          {insider.summary && <p className="text-xs text-slate-300">{insider.summary}</p>}
          {insider.transactions.length > 0 && (
            <ul className="mt-2 space-y-1 border-t border-slate-800 pt-2 text-[11px]">
              {insider.transactions.slice(0, 5).map((t, i) => (
                <li key={i} className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-slate-300">
                    <span
                      className={
                        t.kind === "buy"
                          ? "text-emerald-400"
                          : t.kind === "sell"
                          ? "text-rose-400"
                          : "text-slate-500"
                      }
                    >
                      {t.kind.toUpperCase()}
                    </span>{" "}
                    {t.insider}
                    {t.role ? ` · ${t.role}` : ""}
                  </span>
                  <span className="shrink-0 text-slate-500">
                    {t.value_usd ? `$${(t.value_usd / 1000).toFixed(0)}k` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </AgentCard>

        <AgentCard title="Market signals" status={signals.status} error={signals.error}>
          {signals.sources_used.length > 0 && (
            <p className="mb-2 text-[11px] text-slate-500">
              sources: {signals.sources_used.join(", ")}
            </p>
          )}
          {signals.analyst && (
            <Metric
              label="Analysts"
              value={`${signals.analyst.consensus} (${signals.analyst.score.toFixed(2)})`}
            />
          )}
          {signals.earnings_days !== null && (
            <Metric label="Earnings" value={`~${signals.earnings_days} day(s)`} />
          )}
          {signals.fundamentals?.analyst_target !== null &&
            signals.fundamentals?.analyst_target !== undefined && (
              <Metric
                label="Target"
                value={`$${signals.fundamentals.analyst_target.toFixed(2)}`}
              />
            )}
          {signals.retail && (
            <Metric
              label="Retail"
              value={`${signals.retail.label} (${signals.retail.sample})`}
            />
          )}
          {signals.macro && <Metric label="Macro" value={signals.macro.regime} />}
          {signals.quotes.length > 0 && (
            <ul className="mt-2 space-y-1 border-t border-slate-800 pt-2 text-[11px]">
              {signals.quotes.slice(0, 4).map((q) => (
                <li key={q.source} className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-slate-400">{q.source}</span>
                  <span className="shrink-0 text-slate-200">
                    {q.price !== null ? `$${q.price.toFixed(2)}` : "n/a"}
                    {q.change_pct !== null
                      ? ` ${q.change_pct > 0 ? "+" : ""}${q.change_pct.toFixed(1)}%`
                      : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </AgentCard>
      </div>
    </section>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">{title}</h3>
      <p className="text-sm leading-relaxed text-slate-200">{children}</p>
    </div>
  );
}

function AgentCard({
  title,
  status,
  error,
  children,
}: {
  title: string;
  status: string;
  error: string | null;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-medium">{title}</h3>
        <StatusBadge status={status} />
      </div>
      {error && <p className="mb-2 text-xs text-slate-500">{error}</p>}
      {children}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between text-xs">
      <span className="text-slate-400">{label}</span>
      <span className="font-medium text-slate-200">{value}</span>
    </div>
  );
}
