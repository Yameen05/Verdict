import type {
  AssetCapabilities,
  ConfigStatus,
  ReadinessBody,
  ResearchResponse,
} from "../api/client";
import { InfoTip } from "./InfoTip";

const STATUS_STYLE: Record<string, string> = {
  ok: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  used: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  configured: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  skipped: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  missing: "border-slate-700 bg-slate-900 text-slate-400",
  "n/a": "border-slate-800 bg-slate-950 text-slate-600",
  error: "border-rose-500/40 bg-rose-500/10 text-rose-300",
};

function chip(status: string): string {
  return STATUS_STYLE[status] ?? STATUS_STYLE.missing;
}

export function SourceQualityPanel({
  research,
  readiness,
  config,
  capabilities,
}: {
  research: ResearchResponse | null;
  readiness: ReadinessBody | null;
  config: ConfigStatus | null;
  capabilities: AssetCapabilities | null;
}) {
  // Crypto assets have no filings or insider forms — show those sources as
  // "n/a" instead of "missing" so it doesn't read like a data failure.
  const crypto = capabilities?.asset_class === "crypto";
  const sources = [
    {
      name: "SEC filings",
      status: crypto ? "n/a" : (research?.sec.status ?? "missing"),
      detail: crypto
        ? "coins don't file with the SEC"
        : (research?.sec.error ??
          (research ? `${research.sec.findings.length} findings` : "run Analyze")),
    },
    {
      name: "News",
      status: research?.news.status ?? (config?.sources.newsapi ? "configured" : "missing"),
      detail:
        research?.news.error ??
        (research ? `${research.news.article_count} headlines` : config?.sources.newsapi ? "key set" : "no NewsAPI key"),
    },
    {
      name: "Financials",
      status: research?.metrics.status ?? "missing",
      detail: research?.metrics.error ?? (research ? "Yahoo/yfinance metrics" : "run Analyze"),
    },
    {
      name: "Insiders",
      status: crypto ? "n/a" : (research?.insider.status ?? "missing"),
      detail: crypto
        ? "no insider forms for coins"
        : (research?.insider.error ??
          (research
            ? `${research.insider.buy_count} buys / ${research.insider.sell_count} sells`
            : "run Analyze")),
    },
    {
      name: "Market signals",
      status: research?.signals.status ?? "missing",
      detail:
        research?.signals.error ??
        (research?.signals.sources_used.length
          ? research.signals.sources_used.join(", ")
          : "optional providers"),
    },
  ];

  const signalProviders = config
    ? Object.entries(config.sources.signals).map(([name, enabled]) => ({
        name,
        status: research?.signals.sources_used.includes(name)
          ? "used"
          : enabled
            ? "configured"
            : "missing",
      }))
    : [];

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
      <h3 className="text-sm font-semibold text-slate-100">
        Source quality
        <InfoTip label="Source quality">
          A verdict is stronger when more independent sources are usable. Missing or
          skipped sources do not break the app, but they lower how much evidence it had.
        </InfoTip>
      </h3>
      <div className="mt-3 grid gap-2 md:grid-cols-5">
        {sources.map((s) => (
          <div key={s.name} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              {s.name}
            </div>
            <span
              className={`mt-1 inline-flex rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase ${chip(s.status)}`}
            >
              {s.status}
            </span>
            <div className="mt-1 truncate text-[10px] text-slate-500" title={s.detail}>
              {s.detail}
            </div>
          </div>
        ))}
      </div>

      {signalProviders.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {signalProviders.map((p) => (
            <span
              key={p.name}
              className={`rounded px-2 py-1 text-[10px] font-semibold uppercase ${chip(p.status)}`}
            >
              {p.name}: {p.status}
            </span>
          ))}
        </div>
      )}

      {readiness && (
        <p className="mt-3 text-[11px] text-slate-500">
          Backend readiness:{" "}
          <span className={readiness.status === "ready" ? "text-emerald-300" : "text-amber-300"}>
            {readiness.status}
          </span>
          {Object.entries(readiness.checks).map(([name, check]) => (
            <span key={name}>
              {" "}· {name} {check.ok ? "ok" : check.detail}
            </span>
          ))}
        </p>
      )}
    </section>
  );
}
