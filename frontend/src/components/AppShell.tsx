import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

export type AppSection = "research" | "daytrade" | "analyst" | "history" | "scoreboard";

type ThemeMode = "dark" | "light";
type ReadinessState = "checking" | "ready" | "degraded";

interface Props {
  activeSection: AppSection;
  onSectionChange: (section: AppSection) => void;
  userEmail: string;
  userRole: "owner" | "member";
  onLogout: () => Promise<void>;
  theme: ThemeMode;
  onThemeChange: () => void;
  readiness: { state: ReadinessState; text: string };
  invitesOpen: boolean;
  onInvitesClick: () => void;
  children: ReactNode;
}

const NAV_ITEMS: { id: AppSection; label: string }[] = [
  { id: "research", label: "Research" },
  { id: "daytrade", label: "Day trade" },
  { id: "analyst", label: "Ask analyst" },
  { id: "history", label: "History" },
  { id: "scoreboard", label: "Track record" },
];

function NavIcon({ section }: { section: AppSection }) {
  const common = {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (section === "research") {
    return (
      <svg {...common}>
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4 4M8.5 11h5M11 8.5v5" />
      </svg>
    );
  }
  if (section === "daytrade") {
    return (
      <svg {...common}>
        <path d="M4 17 9 12l3 3 7-8" />
        <path d="M14 7h5v5" />
      </svg>
    );
  }
  if (section === "analyst") {
    return (
      <svg {...common}>
        <path d="M5 5.5h14v10H9l-4 3v-13Z" />
        <path d="M8.5 9.5h7M8.5 12.5h4" />
      </svg>
    );
  }
  if (section === "history") {
    return (
      <svg {...common}>
        <path d="M5 7v5h5" />
        <path d="M6.2 17.8A8 8 0 1 0 5 7" />
        <path d="M12 8v4l2.5 2" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M5 19V10M12 19V5M19 19v-7" />
      <path d="M3 19h18" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden
    >
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

function MenuIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden
    >
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

function AccountPanel({
  userEmail,
  userRole,
  onLogout,
  theme,
  onThemeChange,
  readiness,
  invitesOpen,
  onInvitesClick,
  onClose,
}: Pick<
  Props,
  | "userEmail"
  | "userRole"
  | "onLogout"
  | "theme"
  | "onThemeChange"
  | "readiness"
  | "invitesOpen"
  | "onInvitesClick"
> & { onClose: () => void }) {
  const statusColor =
    readiness.state === "ready"
      ? "bg-emerald-400"
      : readiness.state === "degraded"
        ? "bg-amber-400"
        : "bg-slate-400";

  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-semibold text-slate-50">Your account</p>
        <p className="mt-1 break-all text-sm leading-5 text-slate-400">{userEmail}</p>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-950/55 p-3">
        <div className="flex items-start gap-2.5">
          <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${statusColor}`} />
          <div>
            <p className="text-sm font-medium text-slate-200">System status</p>
            <p className="mt-0.5 text-xs leading-5 text-slate-500">{readiness.text}</p>
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={onThemeChange}
        className="flex min-h-11 w-full items-center justify-between rounded-xl px-3 text-sm font-medium text-slate-300 transition hover:bg-slate-800 hover:text-slate-50"
      >
        <span>Appearance</span>
        <span className="flex items-center gap-2 text-xs text-slate-400">
          {theme === "dark" ? "Dark" : "Light"}
          <span className="relative h-6 w-11 rounded-full border border-slate-700 bg-slate-950">
            <span
              className={`absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full bg-indigo-400 transition ${
                theme === "dark" ? "left-[22px]" : "left-1"
              }`}
            />
          </span>
        </span>
      </button>

      {userRole === "owner" && (
        <button
          type="button"
          onClick={() => {
            onInvitesClick();
            onClose();
          }}
          className={`min-h-11 w-full rounded-xl px-3 text-left text-sm font-medium transition ${
            invitesOpen
              ? "bg-indigo-500/12 text-indigo-300"
              : "text-slate-300 hover:bg-slate-800 hover:text-slate-50"
          }`}
        >
          Manage invitations
        </button>
      )}

      <div className="border-t border-slate-800 pt-3">
        <button
          type="button"
          onClick={() => void onLogout()}
          className="min-h-11 w-full rounded-xl px-3 text-left text-sm font-medium text-rose-300 transition hover:bg-rose-500/10"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

export function AppShell(props: Props) {
  const [accountOpen, setAccountOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);
  const mobileCloseRef = useRef<HTMLButtonElement>(null);
  const mobilePanelRef = useRef<HTMLDivElement>(null);
  const initial = props.userEmail.trim().charAt(0).toUpperCase() || "A";

  useEffect(() => {
    function handlePointer(event: MouseEvent) {
      if (accountRef.current && !accountRef.current.contains(event.target as Node)) {
        setAccountOpen(false);
      }
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setAccountOpen(false);
        setMobileOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [props.activeSection]);

  useEffect(() => {
    if (!mobileOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    mobileCloseRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileOpen]);

  const statusColor =
    props.readiness.state === "ready"
      ? "bg-emerald-400"
      : props.readiness.state === "degraded"
        ? "bg-amber-400"
        : "bg-slate-400";

  function keepFocusInMobileMenu(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab" || !mobilePanelRef.current) return;
    const controls = Array.from(
      mobilePanelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled])',
      ),
    );
    const first = controls[0];
    const last = controls.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-800/70 bg-slate-950/95 px-4 py-5 backdrop-blur lg:flex">
        <div className="flex items-center gap-3 px-2">
          <span className="grid h-10 w-10 place-items-center rounded-xl border border-indigo-400/45 bg-indigo-500/10 pb-0.5 font-display text-xl italic text-indigo-300">
            V
          </span>
          <div>
            <p className="font-display text-xl font-medium tracking-tight text-slate-50">Verdict</p>
            <p className="text-xs text-slate-500">Market research</p>
          </div>
        </div>

        <nav aria-label="Primary" className="mt-9 space-y-1.5">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => props.onSectionChange(item.id)}
              aria-current={props.activeSection === item.id ? "page" : undefined}
              className={`flex min-h-12 w-full items-center gap-3 rounded-xl px-3.5 text-left text-sm font-medium transition ${
                props.activeSection === item.id
                  ? "bg-indigo-500/13 text-indigo-200 ring-1 ring-inset ring-indigo-500/25"
                  : "text-slate-400 hover:bg-slate-900 hover:text-slate-100"
              }`}
            >
              <NavIcon section={item.id} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div ref={accountRef} className="relative mt-auto">
          {accountOpen && (
            <div
              role="dialog"
              aria-label="Account options"
              className="absolute bottom-[calc(100%+0.75rem)] left-0 w-full rounded-2xl border border-slate-700 bg-slate-900 p-4 shadow-2xl shadow-black/40"
            >
              <AccountPanel {...props} onClose={() => setAccountOpen(false)} />
            </div>
          )}
          <button
            type="button"
            onClick={() => setAccountOpen((open) => !open)}
            aria-expanded={accountOpen}
            className="flex min-h-14 w-full items-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/65 px-3 text-left transition hover:border-slate-700 hover:bg-slate-900"
          >
            <span className="relative grid h-9 w-9 shrink-0 place-items-center rounded-full bg-indigo-500/15 text-sm font-bold text-indigo-200">
              {initial}
              <span className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-slate-900 ${statusColor}`} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold text-slate-200">Account</span>
              <span className="block text-xs text-slate-500">Settings and status</span>
            </span>
            <span aria-hidden className="text-slate-500">•••</span>
          </button>
        </div>
      </aside>

      <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-800/70 bg-slate-950/92 px-4 backdrop-blur lg:hidden">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl border border-indigo-400/45 bg-indigo-500/10 pb-0.5 font-display text-lg italic text-indigo-300">
            V
          </span>
          <div>
            <p className="font-display text-lg leading-none text-slate-50">Verdict</p>
            <p className="mt-1 text-xs text-slate-500">
              {NAV_ITEMS.find((item) => item.id === props.activeSection)?.label}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation"
          aria-expanded={mobileOpen}
          className="grid h-11 w-11 place-items-center rounded-xl border border-slate-800 text-slate-300"
        >
          <MenuIcon />
        </button>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-slate-950/75 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <div
            ref={mobilePanelRef}
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            onKeyDown={keepFocusInMobileMenu}
            className="absolute inset-y-0 right-0 flex w-[min(88vw,22rem)] flex-col border-l border-slate-700 bg-slate-900 p-5 shadow-2xl"
          >
            <div className="flex items-center justify-between">
              <p className="font-display text-xl text-slate-50">Menu</p>
              <button
                ref={mobileCloseRef}
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
                className="grid h-11 w-11 place-items-center rounded-xl text-slate-400 hover:bg-slate-800 hover:text-slate-100"
              >
                <CloseIcon />
              </button>
            </div>

            <nav aria-label="Mobile primary" className="mt-6 space-y-1.5">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => props.onSectionChange(item.id)}
                  aria-current={props.activeSection === item.id ? "page" : undefined}
                  className={`flex min-h-12 w-full items-center gap-3 rounded-xl px-3.5 text-left text-sm font-medium transition ${
                    props.activeSection === item.id
                      ? "bg-indigo-500/15 text-indigo-200"
                      : "text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  <NavIcon section={item.id} />
                  <span>{item.label}</span>
                </button>
              ))}
            </nav>

            <div className="mt-auto border-t border-slate-800 pt-5">
              <AccountPanel {...props} onClose={() => setMobileOpen(false)} />
            </div>
          </div>
        </div>
      )}

      <div className="lg:pl-64">{props.children}</div>
    </div>
  );
}
