/** Shared HTTP core: base URL, CSRF header state, and JSON helpers. */

export const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

let csrfToken = "";

export function setCsrfToken(token: string): void {
  csrfToken = token;
}

export function clearCsrfToken(): void {
  csrfToken = "";
}

export function requestHeaders(extra: Record<string, string> = {}): HeadersInit {
  return csrfToken ? { ...extra, "X-CSRF-Token": csrfToken } : extra;
}

export async function errorFromResponse(res: Response): Promise<Error> {
  const text = await res.text();
  let detail = text;
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; request_id?: unknown };
    if (typeof parsed.detail === "string") {
      detail = parsed.request_id
        ? `${parsed.detail} (request ${String(parsed.request_id)})`
        : parsed.detail;
    }
  } catch {
    // Keep the original response text when it is not JSON.
  }
  return new Error(`${res.status} ${res.statusText}: ${detail}`);
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: requestHeaders(),
    credentials: "include",
  });
  if (!res.ok) throw await errorFromResponse(res);
  return (await res.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: requestHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await errorFromResponse(res);
  }
  return (await res.json()) as T;
}

export async function deleteJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "DELETE",
    headers: requestHeaders(),
    credentials: "include",
  });
  if (!res.ok) throw await errorFromResponse(res);
  return (await res.json()) as T;
}
