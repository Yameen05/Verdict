import { useEffect, useMemo, useRef, useState } from "react";
import { LineStyle, PriceScaleMode } from "lightweight-charts";
import {
  api,
  userStateApi,
  type PriceBar,
  type PriceInterval,
  type PriceRange,
  type ResearchResponse,
  type TimingAssessment,
} from "../api/client";
import {
  bollingerBands,
  fmtClock,
  fmtMoney,
  fmtVolume,
  latestOf,
  mergeLiveBar,
  movingAverage,
  toCandles,
  toLineData,
  toPercentSeries,
  toVolumeData,
  macdSeries,
  rsiSeries,
} from "./chart/chartMath";
import {
  ChartHeaderInfo,
  INTERVAL_OPTIONS,
  RANGE_OPTIONS,
  Readout,
  Segmented,
} from "./chart/ChartControls";
import { ChartToolbar, type ChartStyle, type ToggleKey } from "./chart/ChartToolbar";
import { CompareForm } from "./chart/CompareForm";
import { PriceAlerts } from "./chart/PriceAlerts";
import { useChartMarkers, useDecisionLines } from "./chart/useChartOverlays";
import { useChartSetup } from "./chart/useChartSetup";
import { useIndicatorPanes } from "./chart/useIndicatorPanes";

interface Props {
  ticker: string;
  research?: ResearchResponse | null;
  timing?: TimingAssessment | null;
  /** Reports the freshest known price upward (live poll included). */
  onPrice?: (price: number | null) => void;
}

export function StockChartPanel({ ticker, research, timing, onPrice }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const barsRef = useRef<PriceBar[]>([]);
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
  const [showVerdicts, setShowVerdicts] = useState(true);
  const [showEvents, setShowEvents] = useState(true);
  const [showDecisionLines, setShowDecisionLines] = useState(true);

  const {
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
  } = useChartSetup(containerRef, barsRef, setHoverBar);
  const { rsiSeriesRef, macdLineRef, macdSignalRef, macdHistRef } = useIndicatorPanes(
    chartRef,
    barsRef,
    showRsi,
    showMacd,
  );
  useChartMarkers(
    { candleRef, markersRef },
    { ticker, bars, research, showVerdicts, showEvents },
  );
  useDecisionLines(
    { candleRef, overlayLineHandlesRef },
    { bars, research, timing, show: showDecisionLines },
  );

  useEffect(() => {
    barsRef.current = bars;
  }, [bars]);

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
    onPrice?.(latestOf(bars)?.close ?? null);
  }, [bars, onPrice]);

  // ----- history load -----
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

  // ----- push data into every series -----
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
    // Refs are stable; only bars drive updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bars]);

  // ----- toggles -----
  useEffect(() => {
    candleRef.current?.applyOptions({ visible: chartStyle === "candles" });
    areaRef.current?.applyOptions({ visible: chartStyle === "area" });
    lineRef.current?.applyOptions({ visible: chartStyle === "line" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartStyle]);

  useEffect(() => {
    volumeRef.current?.applyOptions({ visible: showVolume });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showVolume]);

  useEffect(() => {
    ma20Ref.current?.applyOptions({ visible: showMa20 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMa20]);

  useEffect(() => {
    ma50Ref.current?.applyOptions({ visible: showMa50 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMa50]);

  useEffect(() => {
    bollBasisRef.current?.applyOptions({ visible: showBoll });
    bollUpperRef.current?.applyOptions({ visible: showBoll });
    bollLowerRef.current?.applyOptions({ visible: showBoll });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showBoll]);

  useEffect(() => {
    // Daily/weekly bars read cleaner as dates only, like TradingView.
    const intraday = !["1D", "1W"].includes(displayedInterval);
    chartRef.current?.timeScale().applyOptions({ timeVisible: intraday });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayedInterval]);

  useEffect(() => {
    chartRef.current?.priceScale("right").applyOptions({
      mode: logScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logScale]);

  // ----- live polling (reads bars via ref so new bars don't reset the timer) -----
  useEffect(() => {
    if (!live) return undefined;
    const pollInterval = window.setInterval(() => {
      if (barsRef.current.length === 0) return;
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
  }, [displayedInterval, live, ticker]);

  // ----- compare overlay -----
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compareTicker, range, interval]);

  // ----- user price levels, stored server-side per account -----
  useEffect(() => {
    let cancelled = false;
    userStateApi
      .levels(ticker)
      .then((res) => {
        if (!cancelled) setPriceLevels(res.prices);
      })
      .catch(() => {
        if (!cancelled) setPriceLevels([]);
      });
    return () => {
      cancelled = true;
    };
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
        color: "#ca8a04",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: fmtMoney(price),
      }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priceLevels, bars.length]);

  function addLevel() {
    const price = activeBar?.close;
    if (price === undefined) return;
    userStateApi
      .addLevel(ticker, Number(price.toFixed(2)))
      .then((res) => setPriceLevels(res.prices))
      .catch(() => {
        // Keep current lines; the next reload will resync.
      });
  }

  function clearLevels() {
    userStateApi
      .clearLevels(ticker)
      .then((res) => setPriceLevels(res.prices))
      .catch(() => {
        // Keep current lines; the next reload will resync.
      });
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

  const toolbarFlags: Record<ToggleKey, boolean> = {
    volume: showVolume,
    ma20: showMa20,
    ma50: showMa50,
    boll: showBoll,
    rsi: showRsi,
    macd: showMacd,
    log: logScale,
    live,
    verdicts: showVerdicts,
    events: showEvents,
    decisionLines: showDecisionLines,
  };
  const toggleSetters: Record<ToggleKey, () => void> = {
    volume: () => setShowVolume((v) => !v),
    ma20: () => setShowMa20((v) => !v),
    ma50: () => setShowMa50((v) => !v),
    boll: () => setShowBoll((v) => !v),
    rsi: () => setShowRsi((v) => !v),
    macd: () => setShowMacd((v) => !v),
    log: () => setLogScale((v) => !v),
    live: () => setLive((v) => !v),
    verdicts: () => setShowVerdicts((v) => !v),
    events: () => setShowEvents((v) => !v),
    decisionLines: () => setShowDecisionLines((v) => !v),
  };

  return (
    <section className="overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
      <header className="border-b border-slate-800 bg-slate-950 px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <ChartHeaderInfo
            ticker={ticker}
            lastClose={stats?.last.close ?? null}
            change={stats?.change ?? null}
            changePct={stats?.changePct ?? null}
            displayedInterval={displayedInterval}
            requestedInterval={interval}
            lastUpdated={lastUpdated}
          />

          <div className="flex flex-wrap gap-2">
            <Segmented options={RANGE_OPTIONS} value={range} onChange={(value) => setRange(value)} />
            <Segmented
              options={INTERVAL_OPTIONS}
              value={interval}
              onChange={(value) => setInterval(value)}
            />
          </div>
        </div>

        <ChartToolbar
          chartStyle={chartStyle}
          onChartStyle={setChartStyle}
          flags={toolbarFlags}
          onToggle={(key) => toggleSetters[key]()}
          levelCount={priceLevels.length}
          onAddLevel={addLevel}
          onClearLevels={clearLevels}
          onResetView={resetView}
        />

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <CompareForm
            input={compareInput}
            onInput={setCompareInput}
            activeTicker={compareTicker}
            error={compareError}
            onSubmit={submitCompare}
            onClear={() => {
              setCompareTicker(null);
              setCompareInput("");
            }}
          />
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
