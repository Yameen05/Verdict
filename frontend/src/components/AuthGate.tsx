import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import {
  authApi,
  setCsrfToken,
  type AuthSession,
  type AuthStatus,
  type LoginChallenge,
  type TwoFactorSetup,
} from "../api/client";
import { LegalModal } from "./LegalModal";

type View =
  | "loading"
  | "login"
  | "bootstrap"
  | "register"
  | "verify"
  | "setup"
  | "recovery"
  | "forgot"
  | "reset"
  | "ready";

interface Props {
  children: (session: AuthSession, logout: () => Promise<void>) => ReactNode;
}

function isChallenge(value: AuthSession | LoginChallenge): value is LoginChallenge {
  return "requires_2fa" in value && value.requires_2fa;
}

export function AuthGate({ children }: Props) {
  const [view, setView] = useState<View>("loading");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [challengeToken, setChallengeToken] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<TwoFactorSetup | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [resetToken, setResetToken] = useState("");
  const setupRequested = useRef(false);

  function acceptSession(next: AuthSession) {
    setCsrfToken(next.csrf_token);
    setSession(next);
    setView(next.requires_2fa_setup ? "setup" : "ready");
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

  useEffect(() => {
    if (view !== "setup" || setup || setupRequested.current) return;
    setupRequested.current = true;
    setBusy(true);
    authApi
      .setupTwoFactor()
      .then(setSetup)
      .catch((e) => setError((e as Error).message))
      .finally(() => setBusy(false));
  }, [view, setup]);

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
        const result = await authApi.login(email, password);
        if (isChallenge(result)) {
          setChallengeToken(result.challenge_token);
          setCode("");
          setView("verify");
        } else {
          acceptSession(result);
        }
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

  async function submitSecondFactor(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      acceptSession(await authApi.verifyTwoFactor(challengeToken, code));
      setChallengeToken("");
      setCode("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function enableTwoFactor(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const result = await authApi.enableTwoFactor(code);
      setCsrfToken(result.csrf_token);
      setSession(result);
      setRecoveryCodes(result.recovery_codes);
      setCode("");
      setView("recovery");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    await authApi.logout();
    setSession(null);
    setSetup(null);
    setupRequested.current = false;
    setRecoveryCodes([]);
    setView("login");
  }

  if (view === "ready" && session) return <>{children(session, logout)}</>;

  if (view === "loading") {
    return <AuthShell title="Securing your session…" subtitle="Checking authentication state." />;
  }

  if (view === "setup") {
    return (
      <AuthShell
        title="Protect your account"
        subtitle="Two-factor authentication is required before financial research is unlocked."
      >
        {setup ? (
          <form className="space-y-5" onSubmit={enableTwoFactor}>
            <div className="rounded-xl bg-white p-4">
              <img
                src={setup.qr_code_data_uri}
                alt="Authenticator QR code"
                className="mx-auto h-52 w-52"
              />
            </div>
            <div>
              <p className="text-xs text-slate-400">
                Scan with 1Password, Bitwarden, Google Authenticator, or another TOTP app.
                If scanning fails, enter this key manually:
              </p>
              <code className="mt-2 block break-all rounded-lg border border-slate-700 bg-slate-950 p-3 text-center text-sm tracking-wider text-cyan-300">
                {setup.secret}
              </code>
            </div>
            <Field
              label="6-digit verification code"
              value={code}
              onChange={setCode}
              autoComplete="one-time-code"
              inputMode="numeric"
              placeholder="123456"
            />
            <ErrorMessage message={error} />
            <SubmitButton busy={busy} label="Enable two-factor authentication" />
          </form>
        ) : (
          <p className="text-sm text-slate-400">{busy ? "Generating a secure key…" : error}</p>
        )}
      </AuthShell>
    );
  }

  if (view === "recovery" && session) {
    const text = recoveryCodes.join("\n");
    return (
      <AuthShell
        title="Save your recovery codes"
        subtitle="Each code works once. Store them in a password manager; they will not be shown again."
      >
        <div className="grid grid-cols-2 gap-2 rounded-xl border border-amber-700/50 bg-amber-950/20 p-4 font-mono text-sm text-amber-100">
          {recoveryCodes.map((recoveryCode) => (
            <span key={recoveryCode}>{recoveryCode}</span>
          ))}
        </div>
        <div className="mt-4 flex gap-3">
          <button
            type="button"
            onClick={() => navigator.clipboard.writeText(text)}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800"
          >
            Copy codes
          </button>
          <button
            type="button"
            onClick={() => setView("ready")}
            className="flex-1 rounded-full bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-400"
          >
            I saved them securely
          </button>
        </div>
      </AuthShell>
    );
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
            placeholder="At least 12 characters"
          />
          <Field
            label="Confirm new password"
            type="password"
            value={confirmPassword}
            onChange={setConfirmPassword}
            autoComplete="new-password"
            placeholder="Repeat your new password"
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

  if (view === "verify") {
    return (
      <AuthShell
        title="Two-factor verification"
        subtitle="Enter your authenticator code or one unused recovery code."
      >
        <form className="space-y-4" onSubmit={submitSecondFactor}>
          <Field
            label="Verification code"
            value={code}
            onChange={setCode}
            autoComplete="one-time-code"
            placeholder="123456 or recovery code"
          />
          <ErrorMessage message={error} />
          <SubmitButton busy={busy} label="Verify and sign in" />
          <button
            type="button"
            onClick={() => {
              setView("login");
              setChallengeToken("");
              setError("");
            }}
            className="w-full text-xs text-slate-400 hover:text-slate-200"
          >
            Back to password sign in
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
          : "Your research data is protected by password and authenticator verification."
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
          />
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
          placeholder={needsNewPassword ? "At least 12 characters" : "Your password"}
        />
        {needsNewPassword && (
          <Field
            label="Confirm password"
            type="password"
            value={confirmPassword}
            onChange={setConfirmPassword}
            autoComplete="new-password"
            placeholder="Repeat your password"
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
        className="mt-1.5 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-white outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
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
