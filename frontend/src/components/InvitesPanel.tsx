import { useEffect, useState } from "react";
import { authApi, type InviteCreated, type InviteEntry } from "../api/client";

const STATUS_CHIP: Record<InviteEntry["status"], string> = {
  pending: "bg-indigo-500/15 text-indigo-300",
  used: "bg-emerald-500/15 text-emerald-300",
  expired: "bg-slate-700/40 text-slate-500",
};

/** Owner-only: mint and manage one-time invite codes for friends. */
export function InvitesPanel({ onClose }: { onClose: () => void }) {
  const [invites, setInvites] = useState<InviteEntry[]>([]);
  const [note, setNote] = useState("");
  const [fresh, setFresh] = useState<InviteCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setInvites((await authApi.listInvites()).invites);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function mint() {
    setBusy(true);
    setError("");
    setCopied(false);
    try {
      const created = await authApi.createInvite(note.trim());
      setFresh(created);
      setNote("");
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: number) {
    try {
      await authApi.revokeInvite(id);
      if (fresh?.id === id) setFresh(null);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="mb-6 rounded-2xl border border-indigo-500/25 bg-slate-900/70 p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-100">
          Invites{" "}
          <span className="font-normal text-slate-500">
            — one-time codes; each creates one member account (valid 7 days)
          </span>
        </h2>
        <button onClick={onClose} className="text-xs text-slate-500 hover:text-slate-300">
          ✕ close
        </button>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="flex-1 min-w-[180px]">
          <label className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Note (who is this for?)
          </label>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={120}
            placeholder="e.g. sara"
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm placeholder-slate-600 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <button
          onClick={mint}
          disabled={busy}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          Mint invite
        </button>
      </div>

      {fresh && (
        <div className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
          <p className="mb-1.5 text-[11px] text-emerald-300">
            Copy this code now — it is shown only once:
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all rounded bg-slate-950 px-2.5 py-1.5 font-mono text-xs text-emerald-200">
              {fresh.code}
            </code>
            <button
              onClick={() => {
                void navigator.clipboard.writeText(fresh.code);
                setCopied(true);
              }}
              className="shrink-0 rounded-md border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
            >
              {copied ? "✓ copied" : "Copy"}
            </button>
          </div>
        </div>
      )}

      {error && <p className="mt-2 text-xs text-rose-400">{error}</p>}

      {invites.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-800/80 border-t border-slate-800/80 text-xs">
          {invites.map((inv) => (
            <li key={inv.id} className="flex items-center gap-3 py-2">
              <span
                className={`rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase ${STATUS_CHIP[inv.status]}`}
              >
                {inv.status}
              </span>
              <span className="min-w-0 flex-1 truncate text-slate-300">
                {inv.note || "(no note)"}
                {inv.used_by_email && (
                  <span className="text-slate-500"> → {inv.used_by_email}</span>
                )}
              </span>
              <span className="shrink-0 text-[10px] text-slate-500">
                {new Date(inv.created_at + (inv.created_at.endsWith("Z") ? "" : "Z")).toLocaleDateString()}
              </span>
              {inv.status === "pending" && (
                <button
                  onClick={() => void revoke(inv.id)}
                  className="shrink-0 text-[10px] text-rose-400 hover:text-rose-300"
                >
                  revoke
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
