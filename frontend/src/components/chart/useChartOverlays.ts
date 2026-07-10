import { useEffect, useState } from "react";
import {
  LineStyle,
  createSeriesMarkers,
  type SeriesMarker,
  type UTCTimestamp,
} from "lightweight-charts";
import {
  api,
  type HistoryEntry,
  type PriceBar,
  type ResearchResponse,
  type TimingAssessment,
} from "../../api/client";
import { latestOf, toTimestamp, verdictMarkers } from "./chartMath";
import type { ChartRefs } from "./useChartSetup";

function numberFrom(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function snapTime(iso: string, bars: PriceBar[]): UTCTimestamp | null {
  if (bars.length === 0) return null;
  const target = toTimestamp(iso);
  const times = bars.map((b) => toTimestamp(b.time));
  const first = times[0];
  const last = times[times.length - 1];
  if (target < first || target > last) return null;
  return (times.find((t) => t >= target) ?? last) as UTCTimestamp;
}

function eventMarkers(
  research: ResearchResponse | null | undefined,
  bars: PriceBar[],
): SeriesMarker<UTCTimestamp>[] {
  if (!research || bars.length === 0) return [];
  const out: SeriesMarker<UTCTimestamp>[] = [];
  for (const headline of research.news.top_headlines.slice(0, 5)) {
    if (!headline.published_at) continue;
    const time = snapTime(headline.published_at, bars);
    if (!time) continue;
    out.push({
      time,
      position: "aboveBar",
      color: "#0284c7",
      shape: "circle",
      text: "News",
    });
  }
  const earnings = research.signals.earnings_days;
  if (earnings !== null && earnings <= 45) {
    out.push({
      time: toTimestamp(bars[bars.length - 1].time),
      position: "aboveBar",
      color: earnings <= 7 ? "#e11d48" : "#d97706",
      shape: "square",
      text: `Earnings +${earnings}d`,
    });
  }
  return out;
}

/**
 * Verdict + news/earnings markers: fetches this ticker's stored verdicts and
 * keeps the marker plugin in sync with the visible bars and toggles.
 */
export function useChartMarkers(
  refs: Pick<ChartRefs, "candleRef" | "markersRef">,
  options: {
    ticker: string;
    bars: PriceBar[];
    research: ResearchResponse | null | undefined;
    showVerdicts: boolean;
    showEvents: boolean;
  },
): void {
  const { ticker, bars, research, showVerdicts, showEvents } = options;
  const [verdicts, setVerdicts] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .history(ticker, 50)
      .then((res) => {
        if (!cancelled) setVerdicts(res.runs);
      })
      .catch(() => {
        if (!cancelled) setVerdicts([]);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  useEffect(() => {
    const series = refs.candleRef.current;
    if (!series) return;
    const markers = [
      ...(showVerdicts ? verdictMarkers(verdicts, bars) : []),
      ...(showEvents ? eventMarkers(research, bars) : []),
    ].sort((a, b) => (a.time as number) - (b.time as number));
    if (refs.markersRef.current) {
      refs.markersRef.current.setMarkers(markers);
    } else {
      refs.markersRef.current = createSeriesMarkers(series, markers);
    }
    // Refs are stable containers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verdicts, bars, showVerdicts, showEvents, research]);
}

/**
 * Decision lines: entry zone, support/resistance, analyst target, and the
 * historical "normal move" band, drawn as horizontal price lines.
 */
export function useDecisionLines(
  refs: Pick<ChartRefs, "candleRef" | "overlayLineHandlesRef">,
  options: {
    bars: PriceBar[];
    research: ResearchResponse | null | undefined;
    timing: TimingAssessment | null | undefined;
    show: boolean;
  },
): void {
  const { bars, research, timing, show } = options;

  useEffect(() => {
    const series = refs.candleRef.current;
    if (!series) return;
    for (const handle of refs.overlayLineHandlesRef.current) {
      series.removePriceLine(handle);
    }
    refs.overlayLineHandlesRef.current = [];
    if (!show) return;

    const latest = latestOf(bars);
    const lines: { price: number | null; title: string; color: string; style?: LineStyle }[] = [];
    const entryLow = timing?.entry_zone_low ?? null;
    const entryHigh = timing?.entry_zone_high ?? null;
    if (entryLow !== null) lines.push({ price: entryLow, title: "Entry low", color: "#0d9488" });
    if (entryHigh !== null) lines.push({ price: entryHigh, title: "Entry high", color: "#0d9488" });

    const support = numberFrom(timing?.technicals.support);
    const resistance = numberFrom(timing?.technicals.resistance);
    if (support !== null) {
      lines.push({ price: support, title: "Support", color: "#059669", style: LineStyle.Dashed });
    }
    if (resistance !== null) {
      lines.push({ price: resistance, title: "Resistance", color: "#e11d48", style: LineStyle.Dashed });
    }

    const target = research?.signals.fundamentals?.analyst_target ?? null;
    if (target !== null) {
      lines.push({ price: target, title: "Analyst target", color: "#9333ea", style: LineStyle.Dashed });
    }

    const swing = research?.metrics.typical_swing_pct ?? null;
    if (latest && swing !== null) {
      lines.push({
        price: latest.close * (1 + swing / 100),
        title: "Normal high",
        color: "#64748b",
        style: LineStyle.Dotted,
      });
      lines.push({
        price: latest.close * (1 - swing / 100),
        title: "Normal low",
        color: "#64748b",
        style: LineStyle.Dotted,
      });
    }

    refs.overlayLineHandlesRef.current = lines
      .filter((line): line is { price: number; title: string; color: string; style?: LineStyle } => line.price !== null)
      .map((line) =>
        series.createPriceLine({
          price: line.price,
          color: line.color,
          lineWidth: 1,
          lineStyle: line.style ?? LineStyle.Solid,
          axisLabelVisible: true,
          title: line.title,
        }),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars, research, show, timing]);
}
