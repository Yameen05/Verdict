/** Authentication + invite endpoints. Re-exported through client.ts. */

import { BASE_URL, clearCsrfToken, errorFromResponse, requestHeaders } from "./http";

export interface AuthUser {
  id: number;
  email: string;
  role: "owner" | "member";
  two_factor_enabled: boolean;
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
  requires_2fa_setup: boolean;
}

export interface LoginChallenge {
  requires_2fa: true;
  challenge_token: string;
}

export interface TwoFactorSetup {
  secret: string;
  provisioning_uri: string;
  qr_code_data_uri: string;
}

export interface TwoFactorEnabled extends AuthSession {
  recovery_codes: string[];
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

export interface AuthStatus {
  bootstrap_required: boolean;
  public_signup_enabled: boolean;
  password_reset_available: boolean;
}

export const authApi = {
  status: () => authJson<AuthStatus>("/auth/status"),
  me: () => authJson<AuthSession>("/auth/me"),
  bootstrap: (
    email: string,
    password: string,
    bootstrapToken: string,
  ) =>
    authJson<AuthSession>("/auth/bootstrap", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Bootstrap-Token": bootstrapToken,
      },
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    authJson<AuthSession | LoginChallenge>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),
  register: (inviteCode: string, email: string, password: string) =>
    authJson<AuthSession>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Omit the code entirely for open-signup registrations.
      body: JSON.stringify({
        ...(inviteCode ? { invite_code: inviteCode } : {}),
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
  verifyTwoFactor: (challengeToken: string, code: string) =>
    authJson<AuthSession>("/auth/2fa/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ challenge_token: challengeToken, code }),
    }),
  setupTwoFactor: () =>
    authJson<TwoFactorSetup>("/auth/2fa/setup", { method: "POST" }),
  enableTwoFactor: (code: string) =>
    authJson<TwoFactorEnabled>("/auth/2fa/enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    }),
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
