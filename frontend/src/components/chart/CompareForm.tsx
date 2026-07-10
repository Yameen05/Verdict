import { COMPARE_COLOR } from "./useChartSetup";

export function CompareForm({
  input,
  onInput,
  activeTicker,
  error,
  onSubmit,
  onClear,
}: {
  input: string;
  onInput: (value: string) => void;
  activeTicker: string | null;
  error: string | null;
  onSubmit: (raw: string) => void;
  onClear: () => void;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(input);
      }}
      className="flex items-center gap-1.5"
    >
      <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Compare
      </span>
      <input
        value={input}
        onChange={(e) => onInput(e.target.value)}
        placeholder="e.g. SPY"
        className="w-24 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs font-medium uppercase text-slate-100 placeholder:text-slate-600 focus:border-fuchsia-500/60 focus:outline-none"
      />
      <button
        type="submit"
        className="rounded-md border border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 hover:border-slate-500 hover:bg-slate-900"
      >
        Add
      </button>
      {activeTicker && (
        <span className="flex items-center gap-1.5 rounded-md border border-fuchsia-500/30 bg-fuchsia-500/10 px-2 py-1 text-xs font-semibold text-fuchsia-300">
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: COMPARE_COLOR }} />
          {activeTicker} · %
          <button
            type="button"
            onClick={onClear}
            className="text-fuchsia-300/70 hover:text-fuchsia-100"
            aria-label="Remove comparison"
          >
            ×
          </button>
        </span>
      )}
      {error && <span className="text-xs text-rose-300">{error}</span>}
    </form>
  );
}
