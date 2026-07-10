import { useEffect, useRef, type MutableRefObject } from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Time,
} from "lightweight-charts";
import type { PriceBar } from "../../api/client";
import { toTimestamp } from "./chartMath";

export const COMPARE_COLOR = "var(--chart-compare)";
export const CHART_HEIGHT = 520;

interface ChartTheme {
  panel: string;
  grid: string;
  text: string;
  axis: string;
  crosshair: string;
  crosshairLabel: string;
  up: string;
  down: string;
  areaLine: string;
  areaTop: string;
  areaBottom: string;
  ma20: string;
  ma50: string;
  compare: string;
}

function cssValue(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function readChartTheme(): ChartTheme {
  return {
    panel: cssValue("--chart-panel", "#07110c"),
    grid: cssValue("--chart-grid", "#183124"),
    text: cssValue("--chart-text", "#96aea0"),
    axis: cssValue("--chart-axis", "#2c4c3a"),
    crosshair: cssValue("--chart-crosshair", "#6b8977"),
    crosshairLabel: cssValue("--chart-crosshair-label", "#0d1d14"),
    up: cssValue("--chart-up", "#22c55e"),
    down: cssValue("--chart-down", "#f43f5e"),
    areaLine: cssValue("--chart-area-line", "#14b8a6"),
    areaTop: cssValue("--chart-area-top", "rgba(20, 184, 166, 0.24)"),
    areaBottom: cssValue("--chart-area-bottom", "rgba(20, 184, 166, 0.03)"),
    ma20: cssValue("--chart-ma20", "#f59e0b"),
    ma50: cssValue("--chart-ma50", "#d946ef"),
    compare: cssValue("--chart-compare", "#d946ef"),
  };
}

export interface ChartRefs {
  chartRef: MutableRefObject<IChartApi | null>;
  candleRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  areaRef: MutableRefObject<ISeriesApi<"Area"> | null>;
  lineRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  volumeRef: MutableRefObject<ISeriesApi<"Histogram"> | null>;
  ma20Ref: MutableRefObject<ISeriesApi<"Line"> | null>;
  ma50Ref: MutableRefObject<ISeriesApi<"Line"> | null>;
  bollBasisRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  bollUpperRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  bollLowerRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  compareRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  priceLineHandlesRef: MutableRefObject<IPriceLine[]>;
  overlayLineHandlesRef: MutableRefObject<IPriceLine[]>;
  markersRef: MutableRefObject<ISeriesMarkersPluginApi<Time> | null>;
}

/**
 * Creates the lightweight-charts instance with every base series (candles,
 * area/line, volume, SMAs, Bollinger, compare overlay), the crosshair→hover
 * wiring, and the resize observer. Runs once per mount; all handles come back
 * as refs so data effects in the panel can feed them.
 */
export function useChartSetup(
  containerRef: MutableRefObject<HTMLDivElement | null>,
  barsRef: MutableRefObject<PriceBar[]>,
  setHoverBar: (bar: PriceBar | null) => void,
): ChartRefs {
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const areaRef = useRef<ISeriesApi<"Area"> | null>(null);
  const lineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ma20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ma50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const bollBasisRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bollUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bollLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const compareRef = useRef<ISeriesApi<"Line"> | null>(null);
  const priceLineHandlesRef = useRef<IPriceLine[]>([]);
  const overlayLineHandlesRef = useRef<IPriceLine[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    const theme = readChartTheme();

    const chart = createChart(container, {
      width: container.clientWidth,
      height: CHART_HEIGHT,
      layout: {
        background: { type: ColorType.Solid, color: theme.panel },
        textColor: theme.text,
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: theme.grid },
        horzLines: { color: theme.grid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: theme.crosshair, labelBackgroundColor: theme.crosshairLabel },
        horzLine: { color: theme.crosshair, labelBackgroundColor: theme.crosshairLabel },
      },
      rightPriceScale: {
        borderColor: theme.axis,
        scaleMargins: { top: 0.08, bottom: 0.24 },
      },
      timeScale: {
        borderColor: theme.axis,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        barSpacing: 8,
        minBarSpacing: 1,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: true,
        axisDoubleClickReset: true,
      },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: theme.up,
      downColor: theme.down,
      borderUpColor: theme.up,
      borderDownColor: theme.down,
      wickUpColor: theme.up,
      wickDownColor: theme.down,
      lastValueVisible: true,
      priceLineVisible: true,
    });
    const area = chart.addSeries(AreaSeries, {
      visible: false,
      lineColor: theme.areaLine,
      topColor: theme.areaTop,
      bottomColor: theme.areaBottom,
      lineWidth: 2,
    });
    const line = chart.addSeries(LineSeries, {
      visible: false,
      color: theme.areaLine,
      lineWidth: 2,
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    const ma20 = chart.addSeries(LineSeries, {
      color: theme.ma20,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const ma50 = chart.addSeries(LineSeries, {
      color: theme.ma50,
      lineWidth: 1,
      visible: false,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const bollBasis = chart.addSeries(LineSeries, {
      color: theme.areaLine,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      visible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const bollUpper = chart.addSeries(LineSeries, {
      color: theme.areaLine,
      lineWidth: 1,
      visible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const bollLower = chart.addSeries(LineSeries, {
      color: theme.areaLine,
      lineWidth: 1,
      visible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    // Compare series lives on its own overlay scale (percent change), so a
    // second ticker can be judged by shape/relative move against the main one.
    const compare = chart.addSeries(LineSeries, {
      priceScaleId: "compare",
      color: theme.compare,
      lineWidth: 2,
      visible: false,
      priceLineVisible: false,
      lastValueVisible: true,
      priceFormat: { type: "custom", formatter: (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%` },
    });
    chart.priceScale("compare").applyOptions({
      scaleMargins: { top: 0.08, bottom: 0.24 },
    });

    chart.priceScale("").applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    });

    const crosshairHandler = (
      param: Parameters<typeof chart.subscribeCrosshairMove>[0] extends (p: infer P) => void
        ? P
        : never,
    ) => {
      const data = param.seriesData.get(candles);
      if (data && "open" in data && "close" in data && param.time !== undefined) {
        const time = Number(param.time);
        const matched = barsRef.current.find((bar) => toTimestamp(bar.time) === time);
        setHoverBar(
          matched ?? {
            time: new Date(time * 1000).toISOString(),
            open: Number(data.open),
            high: Number(data.high),
            low: Number(data.low),
            close: Number(data.close),
            volume: null,
          },
        );
      } else {
        setHoverBar(null);
      }
    };

    chart.subscribeCrosshairMove(crosshairHandler);

    const applyChartTheme = () => {
      const next = readChartTheme();
      chart.applyOptions({
        layout: {
          background: { type: ColorType.Solid, color: next.panel },
          textColor: next.text,
        },
        grid: {
          vertLines: { color: next.grid },
          horzLines: { color: next.grid },
        },
        crosshair: {
          vertLine: { color: next.crosshair, labelBackgroundColor: next.crosshairLabel },
          horzLine: { color: next.crosshair, labelBackgroundColor: next.crosshairLabel },
        },
        rightPriceScale: { borderColor: next.axis },
        timeScale: { borderColor: next.axis },
      });
      candles.applyOptions({
        upColor: next.up,
        downColor: next.down,
        borderUpColor: next.up,
        borderDownColor: next.down,
        wickUpColor: next.up,
        wickDownColor: next.down,
      });
      area.applyOptions({
        lineColor: next.areaLine,
        topColor: next.areaTop,
        bottomColor: next.areaBottom,
      });
      line.applyOptions({ color: next.areaLine });
      ma20.applyOptions({ color: next.ma20 });
      ma50.applyOptions({ color: next.ma50 });
      bollBasis.applyOptions({ color: next.areaLine });
      bollUpper.applyOptions({ color: next.areaLine });
      bollLower.applyOptions({ color: next.areaLine });
      compare.applyOptions({ color: next.compare });
    };

    const themeObserver = new MutationObserver(applyChartTheme);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    const resizeObserver = new ResizeObserver(([entry]) => {
      chart.resize(Math.floor(entry.contentRect.width), CHART_HEIGHT);
    });
    resizeObserver.observe(container);

    chartRef.current = chart;
    candleRef.current = candles;
    areaRef.current = area;
    lineRef.current = line;
    volumeRef.current = volume;
    ma20Ref.current = ma20;
    ma50Ref.current = ma50;
    bollBasisRef.current = bollBasis;
    bollUpperRef.current = bollUpper;
    bollLowerRef.current = bollLower;
    compareRef.current = compare;

    return () => {
      themeObserver.disconnect();
      resizeObserver.disconnect();
      chart.unsubscribeCrosshairMove(crosshairHandler);
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      areaRef.current = null;
      lineRef.current = null;
      volumeRef.current = null;
      ma20Ref.current = null;
      ma50Ref.current = null;
      bollBasisRef.current = null;
      bollUpperRef.current = null;
      bollLowerRef.current = null;
      compareRef.current = null;
      priceLineHandlesRef.current = [];
      overlayLineHandlesRef.current = [];
      markersRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    chartRef,
    candleRef,
    areaRef,
    lineRef,
    volumeRef,
    ma20Ref,
    ma50Ref,
    bollBasisRef,
    bollUpperRef,
    bollLowerRef,
    compareRef,
    priceLineHandlesRef,
    overlayLineHandlesRef,
    markersRef,
  };
}
