import { useEffect, useRef, useState } from "react";
import { authApi } from "../api/auth";

interface GoogleAccounts {
  initialize: (options: {
    client_id: string;
    nonce: string;
    auto_select: boolean;
    callback: (response: { credential: string }) => void;
  }) => void;
  renderButton: (element: HTMLElement, options: {
    type: "standard";
    theme: "outline";
    size: "large";
    text: "signin_with";
    shape: "pill";
    width: number;
  }) => void;
}

function googleAccounts(): GoogleAccounts | undefined {
  return (window as Window & { google?: { accounts?: { id?: GoogleAccounts } } })
    .google?.accounts?.id;
}

let scriptPromise: Promise<GoogleAccounts> | undefined;

function loadGoogle(): Promise<GoogleAccounts> {
  const loaded = googleAccounts();
  if (loaded) return Promise.resolve(loaded);
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<GoogleAccounts>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    const timer = window.setTimeout(fail, 15000);
    function fail() {
      window.clearTimeout(timer);
      script.remove();
      scriptPromise = undefined;
      reject(new Error("Google sign-in couldn't load. You can still sign in with email."));
    }
    script.onerror = fail;
    script.onload = () => {
      const accounts = googleAccounts();
      if (!accounts) return fail();
      window.clearTimeout(timer);
      resolve(accounts);
    };
    document.head.appendChild(script);
  });
  return scriptPromise;
}

export function GoogleSignIn({ clientId, disabled, onCredential }: {
  clientId: string;
  disabled: boolean;
  onCredential: (credential: string) => Promise<void>;
}) {
  const container = useRef<HTMLDivElement>(null);
  const callback = useRef(onCredential);
  callback.current = onCredential;
  const blocked = useRef(disabled);
  blocked.current = disabled;
  const inFlight = useRef(false);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    container.current?.replaceChildren();
    async function prepare() {
      try {
        const google = await loadGoogle();
        if (cancelled) return;
        const { nonce } = await authApi.googleNonce();
        if (cancelled || !container.current) return;
        google.initialize({
          client_id: clientId,
          nonce,
          auto_select: false,
          callback: ({ credential }) => {
            if (cancelled || blocked.current || inFlight.current) return;
            inFlight.current = true;
            void callback.current(credential).catch(() => {
              // Login challenges are single-use, including failed attempts.
              if (!cancelled) setAttempt((value) => value + 1);
            }).finally(() => { inFlight.current = false; });
          },
        });
        google.renderButton(container.current, {
          type: "standard", theme: "outline", size: "large",
          text: "signin_with", shape: "pill",
          width: Math.min(400, container.current.clientWidth),
        });
        setLoading(false);
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message);
          setLoading(false);
        }
      }
    }
    void prepare();
    return () => { cancelled = true; };
  }, [clientId, attempt]);

  return (
    <div className="space-y-3">
      {loading && <p className="text-center text-xs text-slate-400" role="status">Loading Google sign-in…</p>}
      <div ref={container} aria-busy={disabled || loading}
        className={disabled ? "pointer-events-none opacity-60" : ""} />
      {error && (
        <div className="text-center text-xs text-slate-400" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => setAttempt((value) => value + 1)}
            className="mt-2 underline hover:text-slate-200">Try Google again</button>
        </div>
      )}
      <div className="flex items-center gap-3 text-xs text-slate-500" aria-hidden="true">
        <span className="h-px flex-1 bg-slate-800" />or use email<span className="h-px flex-1 bg-slate-800" />
      </div>
    </div>
  );
}
