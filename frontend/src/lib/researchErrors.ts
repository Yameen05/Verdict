export interface FailureInfo {
  kind: "app_daily_limit" | "provider_rate_limit" | "provider_daily_limit" |
    "provider_token_limit" | "provider_limit" | "provider_busy" | "timeout" |
    "connection" | "configuration" | "unknown";
  message: string;
  stage?: string | null;
  window?: "minute" | "day" | null;
  retry_after_seconds?: number | null;
  reset_at?: string | null;
}

const messages: Record<FailureInfo["kind"], string> = {
  app_daily_limit: "Verdict's daily limit for fresh reports and AI requests was reached. The limit resets at midnight UTC; cached reports remain available.",
  provider_rate_limit: "Google's requests-per-minute limit was reached. Wait briefly before trying again; cached reports remain available.",
  provider_daily_limit: "Google's daily AI quota was reached. Retrying shortly is unlikely to help. No reset time was confirmed.",
  provider_token_limit: "Google's AI token quota was reached.",
  provider_limit: "Google rejected the request because of an AI limit. It did not identify whether this is a short rate limit or a longer quota limit, so a short wait may not help.",
  provider_busy: "Google is temporarily busy. Try again later; cached reports remain available.",
  timeout: "The request timed out. Try again later; this research did not finish.",
  connection: "The server could not reach the AI service. Try again when the connection is available.",
  configuration: "The AI service rejected the server's credentials or configuration. The server configuration needs attention before this can succeed.",
  unknown: "The request could not finish. Try again later; cached reports remain available.",
};

/** Structured server categories first. Legacy text is inspected but never displayed. */
export function researchError(error: unknown): string {
  const obj = error && typeof error === "object" ? error as Record<string, unknown> : {};
  const failure = (obj.failure ?? obj.detail ?? obj) as Partial<FailureInfo> | undefined;
  if (failure?.kind && Object.hasOwn(messages, failure.kind)) {
    let message = messages[failure.kind];
    if (failure.kind === "provider_token_limit") {
      message += failure.window === "day"
        ? " This is a daily limit; retrying shortly is unlikely to help. No reset time was confirmed."
        : failure.window === "minute"
        ? " This is a per-minute limit; wait briefly before trying again."
        : " Its window was not identified; a short wait may not help.";
    }
    if (failure.kind === "provider_rate_limit" && typeof failure.retry_after_seconds === "number" && Number.isFinite(failure.retry_after_seconds) && failure.retry_after_seconds >= 0) {
      message += ` The provider suggests waiting at least ${failure.retry_after_seconds} seconds.`;
    }
    return message;
  }
  if (obj.status === 401) return "Your app session expired or access was denied. Sign in again, then retry.";
  if (obj.status === 403) return "The app denied this request. Reload and sign in again before retrying.";
  const raw = typeof error === "string" ? error : String(obj.message ?? obj.detail ?? "");
  const text = raw.toLowerCase();
  if (/midnight utc/.test(text) && /fresh|community/.test(text)) return messages.app_daily_limit;
  if (/401|403|authentication|invalid.api.key|no llm api key|missing credentials/.test(text)) return messages.configuration;
  if (/token/.test(text) && /quota|limit/.test(text)) return researchError({kind:"provider_token_limit",window:/daily|per.?day/.test(text) ? "day" : /per.?minute/.test(text) ? "minute" : null});
  if (/daily|per.?day/.test(text) && /quota|limit/.test(text)) return messages.provider_daily_limit;
  if (/requests.per.minute|rpm|perminuterequests/.test(text)) return messages.provider_rate_limit;
  if (/429|quota|rate.?limit/.test(text)) return messages.provider_limit;
  if (/503|overloaded|capacity/.test(text)) return messages.provider_busy;
  if (/timeout|timed out|504/.test(text)) return messages.timeout;
  if (/connection|failed to fetch|network|stream ended/.test(text)) return messages.connection;
  return messages.unknown;
}
