import { useEffect, useRef, type MutableRefObject } from "react";
import {
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
} from "lightweight-charts";
import type { PriceBar } from "../../api/client";
import { macdSeries, rsiSeries } from "./chartMath";

export interface IndicatorRefs {
  rsiSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  macdLineRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  macdSignalRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  macdHistRef: MutableRefObject<ISeriesApi<"Histogram"> | null>;
}

/**
 * RSI and MACD sub-panes: each is created in its own chart pane when toggled
 * on and torn down when toggled off (lightweight-charts removes the empty
 * pane automatically). Data updates for live bars happen in the panel's bars
 * effect via the returned refs.
 */
export function useIndicatorPanes(
  chartRef: MutableRefObject<IChartApi | null>,
  barsRef: MutableRefObject<PriceBar[]>,
  showRsi: boolean,
  showMacd: boolean,
): IndicatorRefs {
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdHistRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (showRsi && !rsiSeriesRef.current) {
      const pane = chart.addPane();
      const s = chart.addSeries(
        LineSeries,
        {
          color: "#9333ea",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: true,
          priceFormat: { type: "custom", minMove: 0.01, formatter: (v: number) => v.toFixed(0) },
        },
        pane.paneIndex(),
      );
      s.setData(rsiSeries(barsRef.current));
      s.createPriceLine({ price: 70, color: "rgba(220,38,38,0.45)", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "70" });
      s.createPriceLine({ price: 30, color: "rgba(22,163,74,0.45)", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "30" });
      pane.setStretchFactor(0.32);
      rsiSeriesRef.current = s;
    } else if (!showRsi && rsiSeriesRef.current) {
      chart.removeSeries(rsiSeriesRef.current);
      rsiSeriesRef.current = null;
    }
  }, [barsRef, chartRef, showRsi]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (showMacd && !macdLineRef.current) {
      const pane = chart.addPane();
      const idx = pane.paneIndex();
      const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, idx);
      const line = chart.addSeries(LineSeries, { color: "#0d9488", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, idx);
      const signal = chart.addSeries(LineSeries, { color: "#d97706", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, idx);
      const m = macdSeries(barsRef.current);
      hist.setData(m.histogram);
      line.setData(m.macd);
      signal.setData(m.signal);
      pane.setStretchFactor(0.32);
      macdHistRef.current = hist;
      macdLineRef.current = line;
      macdSignalRef.current = signal;
    } else if (!showMacd && macdLineRef.current) {
      if (macdHistRef.current) chart.removeSeries(macdHistRef.current);
      chart.removeSeries(macdLineRef.current);
      if (macdSignalRef.current) chart.removeSeries(macdSignalRef.current);
      macdHistRef.current = null;
      macdLineRef.current = null;
      macdSignalRef.current = null;
    }
  }, [barsRef, chartRef, showMacd]);

  // On unmount the chart itself is destroyed by useChartSetup's cleanup; just
  // drop the dangling handles.
  useEffect(
    () => () => {
      rsiSeriesRef.current = null;
      macdLineRef.current = null;
      macdSignalRef.current = null;
      macdHistRef.current = null;
    },
    [],
  );

  return { rsiSeriesRef, macdLineRef, macdSignalRef, macdHistRef };
}
