import type { ConfigStatus, ReadinessBody } from "../api/client";
import { InfoTip } from "./InfoTip";

function yesNo(value: boolean): string {
  return value ? "on" : "off";
}

export function ApiStatusPanel({
  config,
  readiness,
  lastStatus,
  cachedAgeMinutes,
}: {
  config: ConfigStatus | null;
  readiness: ReadinessBody | null;
  lastStatus: string;
  cachedAgeMinutes: number | null;
}) {
  if (!config && !readiness) return null;

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-950/70 p-4">
      <h3 className="text-sm font-semibold text-slate-100">
        API status
        <InfoTip label="API status">
          This shows configuration and health, not secret key values. Rate-limit
          errors usually come from the LLM provider or this app's per-minute guard.
        </InfoTip>
      </h3>

      <div className="mt-3 grid gap-3 md:grid-cols-4">
        <StatusCard
          label="LLM"
          value={config ? config.llm.model : "—"}
          hint={
            config
              ? `${config.llm.provider} · ${config.llm.configured ? "key set" : "no key"}`
              : "not loaded"
          }
        />
        <StatusCard
          label="Research limit"
          value={config?.llm.rate_limit ?? "—"}
          hint="per IP/request guard"
        />
        <StatusCard
          label="Run cache"
          value={config ? `${config.quotas.research_cache_minutes} min` : "—"}
          hint={
            cachedAgeMinutes !== null
              ? `last result from cache: ${Math.round(cachedAgeMinutes)} min old`
              : "fresh runs use quota"
          }
        />
        <StatusCard
          label="Readiness"
          value={readiness?.status ?? "—"}
          hint={readiness ? Object.keys(readiness.checks).join(", ") : "not checked"}
        />
      </div>

      {config && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Badge label={`NewsAPI ${yesNo(config.sources.newsapi)}`} on={config.sources.newsapi} />
          <Badge label={`Embeddings ${yesNo(config.embeddings.configured)}`} on={config.embeddings.configured} />
          <Badge label={`Vector ${config.sources.vectorstore}`} on />
          {Object.entries(config.sources.signals).map(([name, enabled]) => (
            <Badge key={name} label={`${name} ${yesNo(enabled)}`} on={enabled} />
          ))}
        </div>
      )}

      {lastStatus && (
        <p className="mt-3 rounded-md border border-slate-800 bg-slate-900/60 px-3 py-2 text-[11px] text-slate-400">
          Latest app status: {lastStatus}
        </p>
      )}
    </section>
  );
}

function StatusCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-bold text-slate-100">{value}</div>
      <div className="mt-0.5 truncate text-[10px] text-slate-500" title={hint}>
        {hint}
      </div>
    </div>
  );
}

function Badge({ label, on }: { label: string; on: boolean }) {
  return (
    <span
      className={`rounded px-2 py-1 text-[10px] font-semibold uppercase ${
        on
          ? "border border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
          : "border border-slate-700 bg-slate-900 text-slate-500"
      }`}
    >
      {label}
    </span>
  );
}
