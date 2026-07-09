import type {
  CandlestickData,
  HistogramData,
  LineData,
  SeriesMarker,
  UTCTimestamp,
} from "lightweight-charts";
import type { HistoryEntry, PriceBar } from "../../api/client";

export function fmtMoney(value: number): string {
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: value >= 100 ? 2 : 3,
    maximumFractionDigits: value >= 100 ? 2 : 3,
  })}`;
}

export function fmtSigned(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}`;
}

export function fmtSignedPct(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export function fmtVolume(value: number | null): string {
  if (value === null) return "n/a";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

export function fmtClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function toTimestamp(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

export function toCandles(bars: PriceBar[]): CandlestickData<UTCTimestamp>[] {
  return bars.map((b) => ({
    time: toTimestamp(b.time),
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }));
}

export function toLineData(bars: PriceBar[]): LineData<UTCTimestamp>[] {
  return bars.map((b) => ({ time: toTimestamp(b.time), value: b.close }));
}

export function toVolumeData(bars: PriceBar[]): HistogramData<UTCTimestamp>[] {
  return bars.map((b) => ({
    time: toTimestamp(b.time),
    value: b.volume ?? 0,
    color: b.close >= b.open ? "rgba(34, 197, 94, 0.38)" : "rgba(239, 68, 68, 0.38)",
  }));
}

export function movingAverage(bars: PriceBar[], length: number): LineData<UTCTimestamp>[] {
  const out: LineData<UTCTimestamp>[] = [];
  for (let i = length - 1; i < bars.length; i += 1) {
    const slice = bars.slice(i - length + 1, i + 1);
    const value = slice.reduce((sum, bar) => sum + bar.close, 0) / length;
    out.push({ time: toTimestamp(bars[i].time), value: Number(value.toFixed(4)) });
  }
  return out;
}

export interface BollingerBands {
  basis: LineData<UTCTimestamp>[];
  upper: LineData<UTCTimestamp>[];
  lower: LineData<UTCTimestamp>[];
}

export function bollingerBands(bars: PriceBar[], length = 20, mult = 2): BollingerBands {
  const basis: LineData<UTCTimestamp>[] = [];
  const upper: LineData<UTCTimestamp>[] = [];
  const lower: LineData<UTCTimestamp>[] = [];
  for (let i = length - 1; i < bars.length; i += 1) {
    const slice = bars.slice(i - length + 1, i + 1);
    const mean = slice.reduce((sum, bar) => sum + bar.close, 0) / length;
    const variance =
      slice.reduce((sum, bar) => sum + (bar.close - mean) ** 2, 0) / length;
    const sd = Math.sqrt(variance);
    const time = toTimestamp(bars[i].time);
    basis.push({ time, value: Number(mean.toFixed(4)) });
    upper.push({ time, value: Number((mean + mult * sd).toFixed(4)) });
    lower.push({ time, value: Number((mean - mult * sd).toFixed(4)) });
  }
  return { basis, upper, lower };
}

function emaArray(values: number[], length: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  if (values.length < length) return out;
  const k = 2 / (length + 1);
  let ema = values.slice(0, length).reduce((a, b) => a + b, 0) / length;
  out[length - 1] = ema;
  for (let i = length; i < values.length; i += 1) {
    ema = values[i] * k + ema * (1 - k);
    out[i] = ema;
  }
  return out;
}

/** Wilder's RSI as a full time series (for its own pane). */
export function rsiSeries(bars: PriceBar[], period = 14): LineData<UTCTimestamp>[] {
  const closes = bars.map((b) => b.close);
  const out: LineData<UTCTimestamp>[] = [];
  if (closes.length < period + 1) return out;
  const rsiAt = (ag: number, al: number) => (al === 0 ? 100 : 100 - 100 / (1 + ag / al));
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i <= period; i += 1) {
    const d = closes[i] - closes[i - 1];
    avgGain += Math.max(d, 0);
    avgLoss += Math.max(-d, 0);
  }
  avgGain /= period;
  avgLoss /= period;
  out.push({ time: toTimestamp(bars[period].time), value: Number(rsiAt(avgGain, avgLoss).toFixed(2)) });
  for (let i = period + 1; i < closes.length; i += 1) {
    const d = closes[i] - closes[i - 1];
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period;
    out.push({ time: toTimestamp(bars[i].time), value: Number(rsiAt(avgGain, avgLoss).toFixed(2)) });
  }
  return out;
}

export interface MacdSeries {
  macd: LineData<UTCTimestamp>[];
  signal: LineData<UTCTimestamp>[];
  histogram: HistogramData<UTCTimestamp>[];
}

/** MACD(12,26,9): the line, its signal EMA, and the histogram. */
export function macdSeries(
  bars: PriceBar[],
  fast = 12,
  slow = 26,
  signalLen = 9,
): MacdSeries {
  const closes = bars.map((b) => b.close);
  const emaFast = emaArray(closes, fast);
  const emaSlow = emaArray(closes, slow);
  const defined: { value: number; index: number }[] = [];
  closes.forEach((_, i) => {
    const f = emaFast[i];
    const s = emaSlow[i];
    if (f != null && s != null) defined.push({ value: f - s, index: i });
  });
  const signalVals = emaArray(defined.map((d) => d.value), signalLen);
  const macd: LineData<UTCTimestamp>[] = [];
  const signal: LineData<UTCTimestamp>[] = [];
  const histogram: HistogramData<UTCTimestamp>[] = [];
  defined.forEach((d, j) => {
    const time = toTimestamp(bars[d.index].time);
    macd.push({ time, value: Number(d.value.toFixed(4)) });
    const s = signalVals[j];
    if (s != null) {
      signal.push({ time, value: Number(s.toFixed(4)) });
      const h = d.value - s;
      histogram.push({
        time,
        value: Number(h.toFixed(4)),
        color: h >= 0 ? "rgba(34, 197, 94, 0.5)" : "rgba(239, 68, 68, 0.5)",
      });
    }
  });
  return { macd, signal, histogram };
}

/**
 * Rebase a series to percent change from its first close, so two tickers with
 * very different prices can be compared on one axis (TradingView "compare").
 */
export function toPercentSeries(bars: PriceBar[]): LineData<UTCTimestamp>[] {
  const base = bars.find((b) => b.close > 0)?.close;
  if (!base) return [];
  return bars.map((b) => ({
    time: toTimestamp(b.time),
    value: Number((((b.close - base) / base) * 100).toFixed(4)),
  }));
}

export function latestOf(bars: PriceBar[]): PriceBar | null {
  return bars.length ? bars[bars.length - 1] : null;
}

const VERDICT_STYLE: Record<
  string,
  { color: string; shape: "arrowUp" | "arrowDown" | "circle"; position: "aboveBar" | "belowBar" }
> = {
  Buy: { color: "#22c55e", shape: "arrowUp", position: "belowBar" },
  Sell: { color: "#ef4444", shape: "arrowDown", position: "aboveBar" },
  Hold: { color: "#f59e0b", shape: "circle", position: "aboveBar" },
};

function parseIso(iso: string): number {
  const safe = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`;
  return Math.floor(new Date(safe).getTime() / 1000);
}

/**
 * Verdict overlay (#1): turn stored research verdicts into chart markers,
 * each snapped to the nearest visible bar. Verdicts outside the loaded range
 * are dropped (they'd have nowhere to render).
 */
export function verdictMarkers(
  history: HistoryEntry[],
  bars: PriceBar[],
): SeriesMarker<UTCTimestamp>[] {
  if (bars.length === 0) return [];
  const barTimes = bars.map((b) => toTimestamp(b.time));
  const first = barTimes[0];
  const last = barTimes[barTimes.length - 1];
  const markers: SeriesMarker<UTCTimestamp>[] = [];

  for (const run of history) {
    const style = VERDICT_STYLE[run.recommendation];
    if (!style) continue; // skip Pending
    const t = parseIso(run.created_at);
    if (Number.isNaN(t) || t < first || t > last) continue;
    // Snap to the first bar at/after the verdict time.
    const snapped = barTimes.find((bt) => bt >= t) ?? last;
    const conf = run.confidence != null ? ` ${run.confidence}` : "";
    markers.push({
      time: snapped as UTCTimestamp,
      position: style.position,
      color: style.color,
      shape: style.shape,
      text: `${run.recommendation}${conf}`,
    });
  }
  // lightweight-charts requires markers sorted ascending by time.
  return markers.sort((a, b) => (a.time as number) - (b.time as number));
}

export function mergeLiveBar(previous: PriceBar[], next: PriceBar): PriceBar[] {
  if (previous.length === 0) return [next];
  const nextTime = toTimestamp(next.time);
  const last = previous[previous.length - 1];
  const lastTime = toTimestamp(last.time);
  if (nextTime === lastTime) {
    return [...previous.slice(0, -1), next];
  }
  if (nextTime > lastTime) {
    return [...previous, next];
  }
  return previous.map((bar) => (toTimestamp(bar.time) === nextTime ? next : bar));
}
