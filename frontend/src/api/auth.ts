import legalManifest from "../lib/legalManifest.json";
/** Authentication + invite endpoints. Re-exported through client.ts. */

import { BASE_URL, clearCsrfToken, errorFromResponse, requestHeaders } from "./http";

export interface AuthUser {
  id: number;
  email: string;
  role: "owner" | "member";
}

export interface InviteEntry {
  id: number;
  note: string;
  status: "pending" | "used" | "expired";
  created_at: string;
  expires_at: string;
  used_by_email: string | null;
  used_at: string | null;
}

export interface InviteCreated {
  id: number;
  code: string; // shown exactly once
  note: string;
  expires_at: string;
}

export interface AuthSession {
  user: AuthUser;
  csrf_token: string;
}

async function authJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: requestHeaders((init.headers as Record<string, string> | undefined) ?? {}),
  });
  if (!res.ok) throw await errorFromResponse(res);
  return (await res.json()) as T;
}

export interface LegalManifest {
  versions: { terms: string; risk: string; privacy: string };
  content_sha256: string;
}
export function legalDocumentsCurrent(remote: LegalManifest | undefined): boolean {
  return !!remote && remote.content_sha256 === legalManifest.content_sha256 &&
    Object.entries(legalManifest.versions).every(([key, value]) => remote.versions[key as keyof LegalManifest["versions"]] === value);
}
export function explicitLegalAcceptance() {
  return { accepted: true, terms_version: legalManifest.versions.terms,
    risk_version: legalManifest.versions.risk, privacy_version: legalManifest.versions.privacy,
    content_sha256: legalManifest.content_sha256 };
}

export interface AuthStatus {
  bootstrap_required: boolean;
  legal_manifest: LegalManifest;
  public_signup_enabled: boolean;
  password_reset_available: boolean;
  google_client_id: string | null;
}

export const authApi = {
  status: () => authJson<AuthStatus>("/auth/status"),
  me: () => authJson<AuthSession>("/auth/me"),
  googleNonce: () => authJson<{ nonce: string }>("/auth/google/nonce"),
  googleLogin: (credential: string, inviteCode: string, accepted = false) =>
    authJson<AuthSession>("/auth/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential, invite_code: inviteCode, ...(accepted ? {legal_acceptance: explicitLegalAcceptance()} : {}) }),
    }),
  bootstrap: (
    email: string,
    password: string,
    bootstrapToken: string,
    accepted: boolean,
  ) =>
    authJson<AuthSession>("/auth/bootstrap", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Bootstrap-Token": bootstrapToken,
      },
      body: JSON.stringify({ email, password, ...(accepted ? {legal_acceptance: explicitLegalAcceptance()} : {}) }),
    }),
  login: (email: string, password: string) =>
    authJson<AuthSession>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  register: (inviteCode: string, email: string, password: string, accepted: boolean) =>
    authJson<AuthSession>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Omit the code entirely for open-signup registrations.
      body: JSON.stringify({
        ...(inviteCode ? { invite_code: inviteCode } : {}),
        ...(accepted ? {legal_acceptance: explicitLegalAcceptance()} : {}),
        email,
        password,
      }),
    }),
  requestPasswordReset: async (email: string) => {
    const res = await fetch(`${BASE_URL}/auth/password-reset/request`, {
      method: "POST",
      credentials: "include",
      headers: requestHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw await errorFromResponse(res);
  },
  confirmPasswordReset: async (token: string, password: string) => {
    const res = await fetch(`${BASE_URL}/auth/password-reset/confirm`, {
      method: "POST",
      credentials: "include",
      headers: requestHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ token, password }),
    });
    if (!res.ok) throw await errorFromResponse(res);
  },
  createInvite: (note: string) =>
    authJson<InviteCreated>("/auth/invites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    }),
  listInvites: () => authJson<{ invites: InviteEntry[] }>("/auth/invites"),
  revokeInvite: async (id: number) => {
    const res = await fetch(`${BASE_URL}/auth/invites/${id}`, {
      method: "DELETE",
      credentials: "include",
      headers: requestHeaders(),
    });
    if (!res.ok) throw await errorFromResponse(res);
  },
  logout: async () => {
    const res = await fetch(`${BASE_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: requestHeaders(),
    });
    if (!res.ok && res.status !== 401) throw await errorFromResponse(res);
    clearCsrfToken();
  },
};
