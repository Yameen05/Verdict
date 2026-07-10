import { useEffect, useRef, useState } from "react";
import { api, type ChatTurn, type ResearchResponse } from "../api/client";

interface Props {
  ticker: string;
  research: ResearchResponse | null;
}

type ThreadEntry =
  | { kind: "turn"; turn: ChatTurn }
  | { kind: "error"; message: string };

const SUGGESTED_PROMPT_GROUPS = [
  {
    label: "Money",
    prompts: [
      "If I put $200 in today, what could it be worth in 1 week and 2 weeks?",
      "I bought $100 last week. Am I up or down right now?",
      "If I hold another 2 weeks, what return range should I expect?",
    ],
  },
  {
    label: "Buy / sell",
    prompts: [
      "Should I buy now, wait, or avoid it for a 2-week hold?",
      "If I already own it, should I sell today or keep holding?",
      "What price move would make you change the call?",
    ],
  },
  {
    label: "Understand it",
    prompts: [
      "Explain the verdict like I am new to stocks.",
      "Why this call and not the opposite? What's the other side?",
      "What is the biggest risk that could make it drop?",
      "What would have to happen for you to change the call?",
    ],
  },
];

function friendlyError(raw: string): string {
  const r = raw.toLowerCase();
  // Check quota/billing BEFORE rate-limiting: providers report "out of quota"
  // as a 429/RateLimitError, but retrying never fixes it — so say so plainly.
  if (
    r.includes("insufficient_quota") ||
    r.includes("out of quota") ||
    r.includes("quota") ||
    r.includes("billing")
  ) {
    return "The AI provider quota is used up. Free Gemini API keys still have request limits, so retrying right away may fail again. Wait for the quota window to reset, enable billing for higher limits, or switch to another key/provider.";
  }
  if (r.includes("apiconnectionerror") || r.includes("connection")) {
    return "The backend couldn't reach the AI provider. Usually the API key is missing/invalid, or the server has no internet access.";
  }
  if (r.includes("authentication") || r.includes("401") || r.includes("invalid_api_key")) {
    return "The AI provider rejected the API key. Set a valid LLM_API_KEY in the backend .env and restart.";
  }
  if (r.includes("503")) {
    return "No AI key is configured on the server. Set LLM_API_KEY (and LLM_BASE_URL for Gemini) in the backend .env and restart.";
  }
  if (r.includes("rate") || r.includes("429")) {
    return "Rate-limited. Wait a moment and try again.";
  }
  if (r.includes("502")) {
    return "The AI call failed upstream. Check the backend logs — usually a bad key or network issue.";
  }
  return raw;
}

export function ChatPanel({ ticker, research }: Props) {
  const [thread, setThread] = useState<ThreadEntry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Reset when the user switches tickers — the grounding context changes.
  useEffect(() => {
    setThread([]);
  }, [ticker, research?.report.recommendation]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [thread, busy]);

  function priorTurns(): ChatTurn[] {
    return thread.filter((e): e is { kind: "turn"; turn: ChatTurn } => e.kind === "turn").map(
      (e) => e.turn,
    );
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    const userTurn: ChatTurn = { role: "user", content: trimmed };
    const historyForApi = priorTurns();
    // Add the user message immediately so it stays visible even on failure.
    setThread((t) => [...t, { kind: "turn", turn: userTurn }]);
    setInput("");
    setBusy(true);
    try {
      const res = await api.ask({
        ticker,
        question: trimmed,
        context: research,
        history: historyForApi,
      });
      const answer = res.searched_filing
        ? `${res.answer}\n\n(searched the indexed filing to answer this)`
        : res.answer;
      setThread((t) => [
        ...t,
        { kind: "turn", turn: { role: "assistant", content: answer } },
      ]);
    } catch (e) {
      setThread((t) => [
        ...t,
        { kind: "error", message: friendlyError((e as Error).message || "Request failed") },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function retryLast() {
    // Drop the trailing error, find the last user turn, and resend.
    let cut = thread.length;
    while (cut > 0 && thread[cut - 1].kind === "error") cut--;
    const trimmed = thread.slice(0, cut);
    const lastUser = [...trimmed].reverse().find(
      (e): e is { kind: "turn"; turn: ChatTurn } =>
        e.kind === "turn" && e.turn.role === "user",
    );
    if (!lastUser) return;
    // Remove the previous user turn too — send() will re-add it.
    const without = trimmed.slice(0, trimmed.lastIndexOf(lastUser));
    setThread(without);
    void send(lastUser.turn.content);
  }

  const disabled = !research;

  return (
    <section className="mt-8 rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-6">
      <header className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-100">
            <span className="grid h-7 w-7 place-items-center rounded-full bg-indigo-500/20 text-indigo-300">
              ✦
            </span>
            Ask the analyst
          </h2>
          <p className="mt-1 text-xs text-slate-400">
            Conversational follow-up grounded in the {ticker} report you just generated.
            Ask in plain dollars, like “if I invest $200” or “I invested $100 last week.”
          </p>
        </div>
        {thread.length > 0 && (
          <button
            onClick={() => setThread([])}
            className="text-xs text-slate-500 hover:text-slate-300"
          >
            Clear
          </button>
        )}
      </header>

      {disabled && (
        <div className="rounded-md border border-dashed border-slate-800 bg-slate-950/60 px-4 py-6 text-center text-xs text-slate-500">
          Run a full research report first — the analyst answers based on its findings.
        </div>
      )}

      {!disabled && (
        <>
          <div
            ref={scrollRef}
            className="max-h-[420px] space-y-3 overflow-y-auto pr-1"
          >
            {thread.length === 0 && (
              <div className="space-y-3 rounded-md border border-slate-800 bg-slate-950/40 p-4">
                <p className="text-xs font-medium text-slate-300">Common questions</p>
                <div className="space-y-3">
                  {SUGGESTED_PROMPT_GROUPS.map((group) => (
                    <div key={group.label} className="space-y-1.5">
                      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                        {group.label}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {group.prompts.map((p) => (
                          <button
                            key={p}
                            onClick={() => send(p)}
                            className="max-w-full rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-left text-xs leading-snug text-slate-200 transition hover:border-indigo-500 hover:bg-indigo-500/10 hover:text-indigo-200"
                          >
                            {p}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {thread.map((entry, i) =>
              entry.kind === "turn" ? (
                <Bubble key={i} turn={entry.turn} />
              ) : (
                <ErrorBubble
                  key={i}
                  message={entry.message}
                  onRetry={i === thread.length - 1 ? retryLast : undefined}
                />
              ),
            )}
            {busy && (
              <div className="flex gap-2">
                <Avatar role="assistant" />
                <div className="flex items-center gap-1 rounded-2xl rounded-tl-sm bg-slate-900 px-4 py-3 text-sm">
                  <Dot />
                  <Dot delay="120ms" />
                  <Dot delay="240ms" />
                </div>
              </div>
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="mt-4 flex gap-2"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Ask anything about ${ticker}…`}
              disabled={busy}
              className="flex-1 rounded-full border border-slate-700 bg-slate-950 px-4 py-2 text-sm placeholder-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="rounded-full bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {busy ? "…" : "Send"}
            </button>
          </form>
          <p className="mt-2 text-[10px] text-slate-500">
            Informational only · not investment advice · estimates use the metrics
            already on screen.
          </p>
        </>
      )}
    </section>
  );
}

/**
 * Minimal formatting for assistant text: **bold** segments, "- " bullets as
 * proper bullets, and parenthetical footnotes muted. The prompt asks the model
 * for plain text, but models leak markdown — render it instead of showing
 * literal asterisks.
 */
function FormattedAnswer({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => {
        const bullet = /^\s*[-•]\s+/.test(line);
        const footnote = /^\(.*\)$/.test(line.trim());
        const cleaned = bullet ? line.replace(/^\s*[-•]\s+/, "") : line;
        const parts = cleaned.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
          part.startsWith("**") && part.endsWith("**") ? (
            <strong key={j} className="font-semibold">
              {part.slice(2, -2)}
            </strong>
          ) : (
            <span key={j}>{part}</span>
          ),
        );
        if (bullet) {
          return (
            <div key={i} className="flex gap-1.5">
              <span className="text-indigo-300">•</span>
              <span>{parts}</span>
            </div>
          );
        }
        if (footnote) {
          return (
            <div key={i} className="text-xs italic text-slate-500">
              {parts}
            </div>
          );
        }
        // Preserve blank lines as paragraph spacing.
        return line.trim() === "" ? <div key={i} className="h-2" /> : <div key={i}>{parts}</div>;
      })}
    </>
  );
}

function Bubble({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";
  return (
    <div className={`flex gap-2 ${isUser ? "justify-end" : ""}`}>
      {!isUser && <Avatar role="assistant" />}
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "whitespace-pre-wrap rounded-tr-sm bg-indigo-600 text-white"
            : "rounded-tl-sm bg-slate-900 text-slate-100"
        }`}
      >
        {isUser ? turn.content : <FormattedAnswer text={turn.content} />}
      </div>
      {isUser && <Avatar role="user" />}
    </div>
  );
}

function ErrorBubble({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex gap-2">
      <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-rose-500/20 text-xs text-rose-300">
        ⚠
      </div>
      <div className="max-w-[80%] rounded-2xl rounded-tl-sm border border-rose-900/40 bg-rose-950/40 px-4 py-2.5 text-sm leading-relaxed text-rose-100">
        <div className="font-medium text-rose-200">Couldn't get a response</div>
        <div className="mt-1 text-rose-100/90">{message}</div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-2 rounded-md border border-rose-700/60 px-3 py-1 text-xs text-rose-200 hover:bg-rose-900/40"
          >
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

function Avatar({ role }: { role: "user" | "assistant" }) {
  return (
    <div
      className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-semibold ${
        role === "user"
          ? "bg-slate-700 text-slate-200"
          : "bg-indigo-500/20 text-indigo-300"
      }`}
    >
      {role === "user" ? "You" : "✦"}
    </div>
  );
}

function Dot({ delay = "0ms" }: { delay?: string }) {
  return (
    <span
      style={{ animationDelay: delay }}
      className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500"
    />
  );
}
