import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import {
  authApi,
  setCsrfToken,
  type AuthSession,
  type AuthStatus,
} from "../api/client";
import { LegalModal } from "./LegalModal";
import { GoogleSignIn } from "./GoogleSignIn";

type View =
  | "loading"
  | "login"
  | "bootstrap"
  | "register"
  | "forgot"
  | "reset"
  | "ready";

interface Props {
  children: (session: AuthSession, logout: () => Promise<void>) => ReactNode;
}

export function AuthGate({ children }: Props) {
  const [view, setView] = useState<View>("loading");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [resetToken, setResetToken] = useState("");

  function acceptSession(next: AuthSession) {
    setCsrfToken(next.csrf_token);
    setSession(next);
    setView("ready");
  }

  useEffect(() => {
    let cancelled = false;
    // A reset link (…/?reset_token=…) always lands on the new-password form.
    // The param stays in the URL until the flow ends so the effect is
    // idempotent (StrictMode runs it twice in dev).
    const tokenFromLink = new URLSearchParams(window.location.search).get("reset_token");
    if (tokenFromLink) {
      setResetToken(tokenFromLink);
      setView("reset");
      authApi.status().then((s) => !cancelled && setAuthStatus(s)).catch(() => undefined);
      return () => {
        cancelled = true;
      };
    }
    authApi
      .me()
      .then((value) => {
        if (!cancelled) acceptSession(value);
      })
      .catch(async () => {
        try {
          const status = await authApi.status();
          if (!cancelled) {
            setAuthStatus(status);
            setView(status.bootstrap_required ? "bootstrap" : "login");
          }
        } catch {
          if (!cancelled) {
            setError("The authentication service is unavailable.");
            setView("login");
          }
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submitCredentials(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    if ((view === "bootstrap" || view === "register") && password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      if (view === "bootstrap") {
        acceptSession(await authApi.bootstrap(email, password, bootstrapToken));
      } else if (view === "register") {
        acceptSession(await authApi.register(inviteCode.trim(), email, password));
        setInviteCode("");
      } else {
        acceptSession(await authApi.login(email, password));
      }
      setPassword("");
      setConfirmPassword("");
      setBootstrapToken("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submitForgot(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await authApi.requestPasswordReset(email);
      setNotice(
        "If an account exists for that address, a reset link is on its way. The link works once and expires shortly.",
      );
      setView("login");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function signInWithGoogle(credential: string) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      acceptSession(await authApi.googleLogin(credential, inviteCode.trim()));
      setInviteCode("");
      setPassword("");
      setConfirmPassword("");
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await authApi.confirmPasswordReset(resetToken, password);
      window.history.replaceState(null, "", window.location.pathname);
      setResetToken("");
      setPassword("");
      setConfirmPassword("");
      setNotice("Password updated. Sign in with your new password.");
      setView("login");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await authApi.logout();
    setSession(null);
    setView("login");
  }

  if (view === "ready" && session) return <>{children(session, logout)}</>;

  if (view === "loading") {
    return <AuthShell title="Securing your session…" subtitle="Checking authentication state." />;
  }

  if (view === "forgot") {
    return (
      <AuthShell
        title="Reset your password"
        subtitle="Enter your account email and we'll send a single-use reset link."
      >
        <form className="space-y-4" onSubmit={submitForgot}>
          <Field
            label="Email"
            type="email"
            value={email}
            onChange={setEmail}
            autoComplete="email"
            placeholder="you@example.com"
          />
          <ErrorMessage message={error} />
          <SubmitButton busy={busy} label="Email me a reset link" />
          <button
            type="button"
            onClick={() => {
              setView("login");
              setError("");
            }}
            className="w-full text-xs text-slate-400 hover:text-slate-200"
          >
            Back to sign in
          </button>
        </form>
      </AuthShell>
    );
  }

  if (view === "reset") {
    return (
      <AuthShell
        title="Choose a new password"
        subtitle="This reset link works once. Your other sessions will be signed out."
      >
        <form className="space-y-4" onSubmit={submitReset}>
          <Field
            label="New password"
            type="password"
            value={password}
            onChange={setPassword}
            autoComplete="new-password"
            placeholder="6+ characters, one capital letter and one number"
            minLength={6}
          />
          <Field
            label="Confirm new password"
            type="password"
            value={confirmPassword}
            onChange={setConfirmPassword}
            autoComplete="new-password"
            placeholder="Repeat your new password"
            minLength={6}
          />
          <ErrorMessage message={error} />
          <SubmitButton busy={busy} label="Set new password" />
          <button
            type="button"
            onClick={() => {
              window.history.replaceState(null, "", window.location.pathname);
              setView("login");
              setResetToken("");
              setError("");
            }}
            className="w-full text-xs text-slate-400 hover:text-slate-200"
          >
            Back to sign in
          </button>
        </form>
      </AuthShell>
    );
  }

  const isBootstrap = view === "bootstrap";
  const isRegister = view === "register";
  const publicSignup = authStatus?.public_signup_enabled ?? false;
  const needsNewPassword = isBootstrap || isRegister;
  return (
    <AuthShell
      title={
        isBootstrap
          ? "Create the owner account"
          : isRegister
          ? publicSignup
            ? "Create your account"
            : "Join with an invite"
          : "Sign in to Verdict"
      }
      subtitle={
        isBootstrap
          ? "This one-time setup closes permanently after the first account is created."
          : isRegister
          ? publicSignup
            ? "Free to join. Research runs are shared and daily quotas keep things fair."
            : "Paste the invite code you received to create your account."
          : authStatus?.google_client_id
          ? "Sign in with Google or your email to access your research."
          : "Sign in with your email and password to access your research."
      }
    >
      <form className="space-y-4" onSubmit={submitCredentials}>
        {isRegister && !publicSignup && (
          <Field
            label="Invite code"
            value={inviteCode}
            onChange={setInviteCode}
            autoComplete="off"
            placeholder="Paste your invite code"
            minLength={8}
          />
        )}
        {!isBootstrap && authStatus?.google_client_id && (
          <GoogleSignIn clientId={authStatus.google_client_id} disabled={busy}
            onCredential={signInWithGoogle} />
        )}
        <Field
          label="Email"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          placeholder="you@example.com"
        />
        <Field
          label="Password"
          type="password"
          value={password}
          onChange={setPassword}
          autoComplete={needsNewPassword ? "new-password" : "current-password"}
          placeholder={needsNewPassword ? "6+ characters, one capital letter and one number" : "Your password"}
          minLength={needsNewPassword ? 6 : undefined}
        />
        {needsNewPassword && (
          <Field
            label="Confirm password"
            type="password"
            value={confirmPassword}
            onChange={setConfirmPassword}
            autoComplete="new-password"
            placeholder="Repeat your password"
            minLength={6}
          />
        )}
        {isBootstrap && (
          <Field
            label="One-time bootstrap token"
            type="password"
            value={bootstrapToken}
            onChange={setBootstrapToken}
            autoComplete="off"
            placeholder="From AUTH_BOOTSTRAP_TOKEN"
          />
        )}
        <ErrorMessage message={error} />
        <NoticeMessage message={notice} />
        <SubmitButton
          busy={busy}
          label={
            isBootstrap
              ? "Create owner account"
              : isRegister
              ? "Create my account"
              : "Continue securely"
          }
        />
        {view === "login" && authStatus?.password_reset_available && (
          <button
            type="button"
            onClick={() => {
              setView("forgot");
              setError("");
              setNotice("");
            }}
            className="w-full text-xs text-slate-400 hover:text-slate-200"
          >
            Forgot your password?
          </button>
        )}
        {!isBootstrap && (
          <button
            type="button"
            onClick={() => {
              setView(isRegister ? "login" : "register");
              setError("");
              setNotice("");
            }}
            className="w-full text-xs text-slate-400 hover:text-slate-200"
          >
            {isRegister
              ? "Back to sign in"
              : publicSignup
              ? "New here? Create an account"
              : "Have an invite code? Create an account"}
          </button>
        )}
      </form>
    </AuthShell>
  );
}

function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children?: ReactNode;
}) {
  const [legalOpen, setLegalOpen] = useState(false);
  return (
    <main className="grid min-h-screen place-items-center bg-slate-950 px-6 py-12 text-slate-100">
      <section className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-full border border-indigo-400/50 bg-indigo-500/10 pb-0.5 font-display text-lg italic leading-none text-indigo-300">
            V
          </span>
          <span className="font-display text-2xl tracking-tight text-slate-50">Verdict</span>
        </div>
        <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-7 shadow-2xl shadow-slate-950/60">
          <div className="mb-6">
            <h1 className="font-display text-2xl font-medium tracking-tight text-slate-50">
              {title}
            </h1>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-400">{subtitle}</p>
          </div>
          {children}
        </div>
        <p className="mt-5 text-center text-[11px] italic text-slate-500">
          Every stock gets a trial.
        </p>
        <p className="mt-2 text-center text-[11px] leading-relaxed text-slate-500">
          Educational research tool — not investment advice. By continuing you accept the{" "}
          <button
            type="button"
            onClick={() => setLegalOpen(true)}
            className="underline decoration-slate-600 underline-offset-2 hover:text-slate-300"
          >
            terms, privacy policy, and risk disclosure
          </button>
          .
        </p>
        {legalOpen && <LegalModal onClose={() => setLegalOpen(false)} />}
      </section>
    </main>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  ...props
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  autoComplete?: string;
  inputMode?: "numeric" | "text";
  minLength?: number;
}) {
  return (
    <label className="block text-xs font-medium text-slate-300">
      {label}
      <input
        {...props}
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
        className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
      />
    </label>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return message ? (
    <p role="alert" className="rounded-lg border border-rose-800 bg-rose-950/40 p-3 text-xs text-rose-200">
      {message}
    </p>
  ) : null;
}

function NoticeMessage({ message }: { message: string }) {
  return message ? (
    <p
      role="status"
      className="rounded-lg border border-emerald-800 bg-emerald-950/40 p-3 text-xs text-emerald-200"
    >
      {message}
    </p>
  ) : null;
}

function SubmitButton({ busy, label }: { busy: boolean; label: string }) {
  return (
    <button
      disabled={busy}
      className="w-full rounded-full bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-950/50 transition hover:bg-indigo-500 disabled:opacity-50"
      type="submit"
    >
      {busy ? "Please wait…" : label}
    </button>
  );
}
