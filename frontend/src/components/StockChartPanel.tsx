import { useEffect, useMemo, useRef, useState } from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  PriceScaleMode,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type IPaneApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Time,
} from "lightweight-charts";
import {
  api,
  type HistoryEntry,
  type PriceBar,
  type PriceInterval,
  type PriceRange,
} from "../api/client";
import {
  bollingerBands,
  fmtClock,
  fmtMoney,
  fmtSigned,
  fmtSignedPct,
  fmtVolume,
  latestOf,
  mergeLiveBar,
  movingAverage,
  toCandles,
  toLineData,
  toPercentSeries,
  toTimestamp,
  toVolumeData,
  verdictMarkers,
  macdSeries,
  rsiSeries,
} from "./chart/chartMath";
import { PriceAlerts } from "./chart/PriceAlerts";

interface Props {
  ticker: string;
}

type ChartStyle = "candles" | "area" | "line";

const RANGES: { value: PriceRange; label: string }[] = [
  { value: "1D", label: "1D" },
  { value: "5D", label: "5D" },
  { value: "1M", label: "1M" },
  { value: "3M", label: "3M" },
  { value: "6M", label: "6M" },
  { value: "1Y", label: "1Y" },
  { value: "5Y", label: "5Y" },
];

const INTERVALS: { value: PriceInterval; label: string }[] = [
  { value: "1M", label: "1m" },
  { value: "5M", label: "5m" },
  { value: "15M", label: "15m" },
  { value: "1H", label: "1h" },
  { value: "1D", label: "1D" },
  { value: "1W", label: "1W" },
];

const UP = "#22c55e";
const DOWN = "#ef4444";
const GRID = "#1e293b";
const PANEL = "#020617";
const COMPARE_COLOR = "#e879f9";

export function StockChartPanel({ ticker }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
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
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const rsiPaneRef = useRef<IPaneApi<Time> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdPaneRef = useRef<IPaneApi<Time> | null>(null);
  const macdLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdSignalRef = useRef<ISeriesApi<"Line"> | null>(null);
  const macdHistRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const fitOnNextDataRef = useRef(false);

  const [range, setRange] = useState<PriceRange>("1D");
  const [interval, setInterval] = useState<PriceInterval>("1M");
  const [actualInterval, setActualInterval] = useState<PriceInterval>("1M");
  const [chartStyle, setChartStyle] = useState<ChartStyle>("candles");
  const [bars, setBars] = useState<PriceBar[]>([]);
  const [hoverBar, setHoverBar] = useState<PriceBar | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showVolume, setShowVolume] = useState(true);
  const [showMa20, setShowMa20] = useState(true);
  const [showMa50, setShowMa50] = useState(false);
  const [showBoll, setShowBoll] = useState(false);
  const [showRsi, setShowRsi] = useState(false);
  const [showMacd, setShowMacd] = useState(false);
  const [logScale, setLogScale] = useState(false);
  const [live, setLive] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [compareTicker, setCompareTicker] = useState<string | null>(null);
  const [compareInput, setCompareInput] = useState("");
  const [compareError, setCompareError] = useState<string | null>(null);
  const [priceLevels, setPriceLevels] = useState<number[]>([]);
  const [verdicts, setVerdicts] = useState<HistoryEntry[]>([]);
  const [showVerdicts, setShowVerdicts] = useState(true);

  const stats = useMemo(() => {
    const first = bars[0] ?? null;
    const last = latestOf(bars);
    if (!first || !last) return null;
    const change = last.close - first.close;
    const changePct = (change / first.close) * 100;
    const high = Math.max(...bars.map((b) => b.high));
    const low = Math.min(...bars.map((b) => b.low));
    const volumes = bars.map((b) => b.volume ?? 0).filter((v) => v > 0);
    const avgVolume = volumes.length
      ? volumes.reduce((sum, value) => sum + value, 0) / volumes.length
      : null;
    return { first, last, change, changePct, high, low, avgVolume };
  }, [bars]);

  const activeBar = hoverBar ?? latestOf(bars);
  const activeUp = activeBar ? activeBar.close >= activeBar.open : true;
  const displayedInterval = actualInterval ?? interval;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 520,
      layout: {
        background: { type: ColorType.Solid, color: PANEL },
        textColor: "#94a3b8",
        fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: GRID },
        horzLines: { color: GRID },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#64748b", labelBackgroundColor: "#1e293b" },
        horzLine: { color: "#64748b", labelBackgroundColor: "#1e293b" },
      },
      rightPriceScale: {
        borderColor: "#334155",
        scaleMargins: { top: 0.08, bottom: 0.24 },
      },
      timeScale: {
        borderColor: "#334155",
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
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
      lastValueVisible: true,
      priceLineVisible: true,
    });
    const area = chart.addSeries(AreaSeries, {
      visible: false,
      lineColor: "#38bdf8",
      topColor: "rgba(56, 189, 248, 0.34)",
      bottomColor: "rgba(56, 189, 248, 0.02)",
      lineWidth: 2,
    });
    const line = chart.addSeries(LineSeries, {
      visible: false,
      color: "#38bdf8",
      lineWidth: 2,
    });
    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    const ma20 = chart.addSeries(LineSeries, {
      color: "#f59e0b",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const ma50 = chart.addSeries(LineSeries, {
      color: "#a78bfa",
      lineWidth: 1,
      visible: false,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const bollBasis = chart.addSeries(LineSeries, {
      color: "#38bdf8",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      visible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const bollUpper = chart.addSeries(LineSeries, {
      color: "rgba(56, 189, 248, 0.55)",
      lineWidth: 1,
      visible: false,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const bollLower = chart.addSeries(LineSeries, {
      color: "rgba(56, 189, 248, 0.55)",
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
      color: COMPARE_COLOR,
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

    const crosshairHandler = (param: Parameters<typeof chart.subscribeCrosshairMove>[0] extends (p: infer P) => void ? P : never) => {
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

    const resizeObserver = new ResizeObserver(([entry]) => {
      chart.resize(Math.floor(entry.contentRect.width), 520);
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
      markersRef.current = null;
      rsiSeriesRef.current = null;
      rsiPaneRef.current = null;
      macdHistRef.current = null;
      macdLineRef.current = null;
      macdSignalRef.current = null;
      macdPaneRef.current = null;
    };
  }, []);

  const barsRef = useRef<PriceBar[]>([]);
  useEffect(() => {
    barsRef.current = bars;
  }, [bars]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setHoverBar(null);
    api
      .priceHistory(ticker, range, interval)
      .then((res) => {
        if (cancelled) return;
        fitOnNextDataRef.current = true;
        setBars(res.bars);
        setActualInterval(res.interval ?? interval);
        setLastUpdated(new Date().toISOString());
      })
      .catch((e) => {
        if (cancelled) return;
        setBars([]);
        setError(e instanceof Error ? e.message : "Unable to load price chart");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, range, interval]);

  useEffect(() => {
    const candles = toCandles(bars);
    const closes = toLineData(bars);
    candleRef.current?.setData(candles);
    areaRef.current?.setData(closes);
    lineRef.current?.setData(closes);
    volumeRef.current?.setData(toVolumeData(bars));
    ma20Ref.current?.setData(movingAverage(bars, 20));
    ma50Ref.current?.setData(movingAverage(bars, 50));
    const boll = bollingerBands(bars, 20, 2);
    bollBasisRef.current?.setData(boll.basis);
    bollUpperRef.current?.setData(boll.upper);
    bollLowerRef.current?.setData(boll.lower);
    rsiSeriesRef.current?.setData(rsiSeries(bars));
    if (macdLineRef.current) {
      const m = macdSeries(bars);
      macdHistRef.current?.setData(m.histogram);
      macdLineRef.current.setData(m.macd);
      macdSignalRef.current?.setData(m.signal);
    }
    if (bars.length > 0 && fitOnNextDataRef.current) {
      chartRef.current?.timeScale().fitContent();
      fitOnNextDataRef.current = false;
    }
  }, [bars]);

  useEffect(() => {
    candleRef.current?.applyOptions({ visible: chartStyle === "candles" });
    areaRef.current?.applyOptions({ visible: chartStyle === "area" });
    lineRef.current?.applyOptions({ visible: chartStyle === "line" });
  }, [chartStyle]);

  useEffect(() => {
    volumeRef.current?.applyOptions({ visible: showVolume });
  }, [showVolume]);

  useEffect(() => {
    ma20Ref.current?.applyOptions({ visible: showMa20 });
  }, [showMa20]);

  useEffect(() => {
    ma50Ref.current?.applyOptions({ visible: showMa50 });
  }, [showMa50]);

  useEffect(() => {
    bollBasisRef.current?.applyOptions({ visible: showBoll });
    bollUpperRef.current?.applyOptions({ visible: showBoll });
    bollLowerRef.current?.applyOptions({ visible: showBoll });
  }, [showBoll]);

  // --- RSI sub-pane (#2): its own pane, created/destroyed on toggle ---
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (showRsi && !rsiSeriesRef.current) {
      const pane = chart.addPane();
      const s = chart.addSeries(
        LineSeries,
        {
          color: "#c084fc",
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: true,
          priceFormat: { type: "custom", minMove: 0.01, formatter: (v: number) => v.toFixed(0) },
        },
        pane.paneIndex(),
      );
      s.setData(rsiSeries(barsRef.current));
      s.createPriceLine({ price: 70, color: "rgba(239,68,68,0.4)", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "70" });
      s.createPriceLine({ price: 30, color: "rgba(34,197,94,0.4)", lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "30" });
      pane.setStretchFactor(0.32);
      rsiPaneRef.current = pane;
      rsiSeriesRef.current = s;
    } else if (!showRsi && rsiSeriesRef.current) {
      chart.removeSeries(rsiSeriesRef.current);
      rsiSeriesRef.current = null;
      rsiPaneRef.current = null;
    }
  }, [showRsi]);

  // --- MACD sub-pane (#2): line + signal + histogram in its own pane ---
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (showMacd && !macdLineRef.current) {
      const pane = chart.addPane();
      const idx = pane.paneIndex();
      const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, idx);
      const line = chart.addSeries(LineSeries, { color: "#38bdf8", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, idx);
      const signal = chart.addSeries(LineSeries, { color: "#f59e0b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, idx);
      const m = macdSeries(barsRef.current);
      hist.setData(m.histogram);
      line.setData(m.macd);
      signal.setData(m.signal);
      pane.setStretchFactor(0.32);
      macdPaneRef.current = pane;
      macdHistRef.current = hist;
      macdLineRef.current = line;
      macdSignalRef.current = signal;
    } else if (!showMacd && macdLineRef.current) {
      if (macdHistRef.current) chart.removeSeries(macdHistRef.current);
      if (macdLineRef.current) chart.removeSeries(macdLineRef.current);
      if (macdSignalRef.current) chart.removeSeries(macdSignalRef.current);
      macdHistRef.current = null;
      macdLineRef.current = null;
      macdSignalRef.current = null;
      macdPaneRef.current = null;
    }
  }, [showMacd]);

  useEffect(() => {
    // Daily/weekly bars read cleaner as dates only, like TradingView.
    const intraday = !["1D", "1W"].includes(displayedInterval);
    chartRef.current?.timeScale().applyOptions({ timeVisible: intraday });
  }, [displayedInterval]);

  useEffect(() => {
    chartRef.current?.priceScale("right").applyOptions({
      mode: logScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
    });
  }, [logScale]);

  useEffect(() => {
    if (!live || bars.length === 0) return undefined;
    const pollInterval = window.setInterval(() => {
      const quoteInterval = displayedInterval === "1W" ? "1D" : displayedInterval;
      api
        .latestPrice(ticker, quoteInterval)
        .then((res) => {
          setBars((current) => mergeLiveBar(current, res.bar));
          setActualInterval(res.interval ?? quoteInterval);
          setLastUpdated(new Date().toISOString());
        })
        .catch(() => {
          // Keep the last loaded chart visible; the next poll may recover.
        });
    }, 15_000);
    return () => window.clearInterval(pollInterval);
  }, [bars.length, displayedInterval, live, ticker]);

  // --- Compare mode (#3): overlay a second ticker as % change ---
  useEffect(() => {
    if (!compareTicker) {
      compareRef.current?.setData([]);
      compareRef.current?.applyOptions({ visible: false });
      return undefined;
    }
    let cancelled = false;
    setCompareError(null);
    api
      .priceHistory(compareTicker, range, interval)
      .then((res) => {
        if (cancelled) return;
        compareRef.current?.setData(toPercentSeries(res.bars));
        compareRef.current?.applyOptions({ visible: true });
      })
      .catch((e) => {
        if (cancelled) return;
        setCompareError(e instanceof Error ? e.message : "Compare failed");
        setCompareTicker(null);
      });
    return () => {
      cancelled = true;
    };
  }, [compareTicker, range, interval]);

  // --- Verdict overlay (#1): fetch this ticker's past verdicts ---
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
    const series = candleRef.current;
    if (!series) return;
    const markers = showVerdicts ? verdictMarkers(verdicts, bars) : [];
    if (markersRef.current) {
      markersRef.current.setMarkers(markers);
    } else {
      markersRef.current = createSeriesMarkers(series, markers);
    }
  }, [verdicts, bars, showVerdicts]);

  // --- Drawing tools (#5): horizontal price levels, persisted per ticker ---
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(`verdict.levels.${ticker}`);
      setPriceLevels(raw ? (JSON.parse(raw) as number[]) : []);
    } catch {
      setPriceLevels([]);
    }
  }, [ticker]);

  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;
    for (const handle of priceLineHandlesRef.current) {
      series.removePriceLine(handle);
    }
    priceLineHandlesRef.current = priceLevels.map((price) =>
      series.createPriceLine({
        price,
        color: "#eab308",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: fmtMoney(price),
      }),
    );
    try {
      window.localStorage.setItem(`verdict.levels.${ticker}`, JSON.stringify(priceLevels));
    } catch {
      // localStorage unavailable (private mode) — lines still render this session.
    }
  }, [priceLevels, ticker, bars.length]);

  function addLevel() {
    const price = activeBar?.close;
    if (price === undefined) return;
    const rounded = Number(price.toFixed(2));
    setPriceLevels((prev) => (prev.includes(rounded) ? prev : [...prev, rounded]));
  }

  function clearLevels() {
    setPriceLevels([]);
  }

  function submitCompare(raw: string) {
    const next = raw.trim().toUpperCase();
    setCompareError(null);
    if (!next) {
      setCompareTicker(null);
      return;
    }
    if (next === ticker) {
      setCompareError("Already showing this ticker");
      return;
    }
    setCompareTicker(next);
  }

  function resetView() {
    chartRef.current?.timeScale().fitContent();
  }

  const changeClass =
    stats && stats.change >= 0 ? "text-emerald-300" : "text-rose-300";

  return (
    <section className="overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
      <header className="border-b border-slate-800 bg-slate-950 px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-baseline gap-3">
              <h2 className="font-mono text-2xl font-semibold text-slate-100">{ticker}</h2>
              {stats && (
                <>
                  <span className="text-2xl font-semibold text-slate-100">
                    {fmtMoney(stats.last.close)}
                  </span>
                  <span className={`text-sm font-semibold ${changeClass}`}>
                    {fmtSigned(stats.change)} ({fmtSignedPct(stats.changePct)})
                  </span>
                </>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
              <span>Yahoo Finance</span>
              <span>·</span>
              <span>{displayedInterval.toLowerCase()} bars</span>
              {displayedInterval !== interval && (
                <>
                  <span>·</span>
                  <span>using {displayedInterval.toLowerCase()}</span>
                </>
              )}
              {lastUpdated && (
                <>
                  <span>·</span>
                  <span>updated {new Date(lastUpdated).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>
                </>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Segmented
              options={RANGES}
              value={range}
              onChange={(value) => setRange(value)}
            />
            <Segmented
              options={INTERVALS}
              value={interval}
              onChange={(value) => setInterval(value)}
            />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <ToolbarButton active={chartStyle === "candles"} onClick={() => setChartStyle("candles")}>
            Candles
          </ToolbarButton>
          <ToolbarButton active={chartStyle === "area"} onClick={() => setChartStyle("area")}>
            Area
          </ToolbarButton>
          <ToolbarButton active={chartStyle === "line"} onClick={() => setChartStyle("line")}>
            Line
          </ToolbarButton>
          <ToolbarButton active={showVolume} onClick={() => setShowVolume((v) => !v)}>
            Volume
          </ToolbarButton>
          <ToolbarButton active={showMa20} onClick={() => setShowMa20((v) => !v)}>
            SMA 20
          </ToolbarButton>
          <ToolbarButton active={showMa50} onClick={() => setShowMa50((v) => !v)}>
            SMA 50
          </ToolbarButton>
          <ToolbarButton active={showBoll} onClick={() => setShowBoll((v) => !v)}>
            Boll
          </ToolbarButton>
          <ToolbarButton active={showRsi} onClick={() => setShowRsi((v) => !v)}>
            RSI
          </ToolbarButton>
          <ToolbarButton active={showMacd} onClick={() => setShowMacd((v) => !v)}>
            MACD
          </ToolbarButton>
          <ToolbarButton active={logScale} onClick={() => setLogScale((v) => !v)}>
            Log
          </ToolbarButton>
          <ToolbarButton active={live} onClick={() => setLive((v) => !v)}>
            Live
          </ToolbarButton>
          <ToolbarButton active={showVerdicts} onClick={() => setShowVerdicts((v) => !v)}>
            Verdicts
          </ToolbarButton>
          <button
            type="button"
            onClick={addLevel}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-slate-500 hover:bg-slate-900"
          >
            + Level
          </button>
          {priceLevels.length > 0 && (
            <button
              type="button"
              onClick={clearLevels}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-amber-300 hover:border-amber-500/60 hover:bg-slate-900"
            >
              Clear {priceLevels.length} line{priceLevels.length > 1 ? "s" : ""}
            </button>
          )}
          <button
            type="button"
            onClick={resetView}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-slate-500 hover:bg-slate-900"
          >
            Reset
          </button>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submitCompare(compareInput);
            }}
            className="flex items-center gap-1.5"
          >
            <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Compare
            </span>
            <input
              value={compareInput}
              onChange={(e) => setCompareInput(e.target.value)}
              placeholder="e.g. SPY"
              className="w-24 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs font-medium uppercase text-slate-100 placeholder:text-slate-600 focus:border-fuchsia-500/60 focus:outline-none"
            />
            <button
              type="submit"
              className="rounded-md border border-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 hover:border-slate-500 hover:bg-slate-900"
            >
              Add
            </button>
            {compareTicker && (
              <span className="flex items-center gap-1.5 rounded-md border border-fuchsia-500/30 bg-fuchsia-500/10 px-2 py-1 text-xs font-semibold text-fuchsia-300">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: COMPARE_COLOR }} />
                {compareTicker} · %
                <button
                  type="button"
                  onClick={() => {
                    setCompareTicker(null);
                    setCompareInput("");
                  }}
                  className="text-fuchsia-300/70 hover:text-fuchsia-100"
                  aria-label="Remove comparison"
                >
                  ×
                </button>
              </span>
            )}
            {compareError && <span className="text-xs text-rose-300">{compareError}</span>}
          </form>
        </div>
      </header>

      <div className="grid border-b border-slate-800 bg-slate-950/80 text-xs md:grid-cols-6">
        <Readout label="Open" value={activeBar ? fmtMoney(activeBar.open) : "n/a"} />
        <Readout
          label="High"
          value={activeBar ? fmtMoney(activeBar.high) : "n/a"}
          valueClass="text-emerald-300"
        />
        <Readout
          label="Low"
          value={activeBar ? fmtMoney(activeBar.low) : "n/a"}
          valueClass="text-rose-300"
        />
        <Readout
          label="Close"
          value={activeBar ? fmtMoney(activeBar.close) : "n/a"}
          valueClass={activeUp ? "text-emerald-300" : "text-rose-300"}
        />
        <Readout label="Volume" value={activeBar ? fmtVolume(activeBar.volume) : "n/a"} />
        <Readout label="Time" value={activeBar ? fmtClock(activeBar.time) : "n/a"} />
      </div>

      <div className="relative">
        <div ref={containerRef} className="h-[520px] w-full" />
        {loading && (
          <div className="absolute inset-0 grid place-items-center bg-slate-950/70 text-sm text-slate-400">
            Loading market data…
          </div>
        )}
        {!loading && error && (
          <div className="absolute inset-0 grid place-items-center bg-slate-950 px-6 text-center text-sm text-rose-300">
            Chart unavailable: {error}
          </div>
        )}
        {live && !error && (
          <div className="pointer-events-none absolute right-4 top-4 flex items-center gap-2 rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />
            Live
          </div>
        )}
      </div>

      {stats && (
        <div className="grid border-t border-slate-800 bg-slate-950/90 text-xs md:grid-cols-4">
          <Readout label="Range high" value={fmtMoney(stats.high)} />
          <Readout label="Range low" value={fmtMoney(stats.low)} />
          <Readout label="Avg volume" value={fmtVolume(stats.avgVolume)} />
          <Readout label="Bars" value={String(bars.length)} />
        </div>
      )}

      <PriceAlerts ticker={ticker} price={stats?.last.close ?? null} />
    </section>
  );
}

function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex rounded-md border border-slate-800 bg-slate-900 p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`rounded px-2.5 py-1.5 text-xs font-semibold transition ${
            value === option.value
              ? "bg-slate-100 text-slate-950"
              : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function ToolbarButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border px-3 py-1.5 text-xs font-medium transition ${
        active
          ? "border-cyan-500/60 bg-cyan-500/10 text-cyan-200"
          : "border-slate-700 text-slate-400 hover:border-slate-500 hover:bg-slate-900 hover:text-slate-100"
      }`}
    >
      {children}
    </button>
  );
}

function Readout({
  label,
  value,
  valueClass = "text-slate-200",
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="border-r border-slate-800 px-3 py-2 last:border-r-0">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-600">
        {label}
      </div>
      <div className={`mt-0.5 truncate font-medium ${valueClass}`}>{value}</div>
    </div>
  );
}
