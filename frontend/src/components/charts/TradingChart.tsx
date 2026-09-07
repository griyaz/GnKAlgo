"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
} from "lightweight-charts";

import {
  type Candle,
  emaSeries,
  rsiSeries,
  supertrendSeries,
  updateCandleBucket,
} from "@/lib/indicators";
import {
  TIMEFRAMES,
  type ChartSettings,
  type TimeframeId,
} from "@/lib/chartSettings";
import { fetchCandles } from "@/services/chartDataService";
import { marketWebSocket } from "@/services/marketWebSocket";

import { chartColors, EMA_COLORS } from "./chartTheme";
import { ChartError } from "./ChartError";
import { ChartLoading } from "./ChartLoading";

export type CrosshairPayload = {
  o?: number;
  h?: number;
  l?: number;
  c?: number;
  vol?: number | null;
  changePct?: number;
};

function toUtc(t: number): UTCTimestamp {
  return t as UTCTimestamp;
}

function intervalSec(tf: TimeframeId): number {
  return TIMEFRAMES.find((x) => x.id === tf)?.seconds ?? 300;
}

function buildEmaData(candles: Candle[], period: number): LineData[] {
  const closes = candles.map((c) => c.close);
  const series = emaSeries(closes, period);
  const out: LineData[] = [];
  for (let i = 0; i < candles.length; i++) {
    if (series[i] != null) out.push({ time: toUtc(candles[i].time), value: series[i]! });
  }
  return out;
}

function buildRsiData(candles: Candle[], period: number): LineData[] {
  const closes = candles.map((c) => c.close);
  const series = rsiSeries(closes, period);
  const out: LineData[] = [];
  for (let i = 0; i < candles.length; i++) {
    if (series[i] != null) out.push({ time: toUtc(candles[i].time), value: series[i]! });
  }
  return out;
}

function buildVolumeData(candles: Candle[]): HistogramData[] {
  const colors = chartColors();
  return candles
    .filter((c) => c.volume != null)
    .map((c) => ({
      time: toUtc(c.time),
      value: c.volume!,
      color: c.close >= c.open ? colors.profit + "55" : colors.loss + "55",
    }));
}

export function TradingChart({
  symbol,
  exchange,
  timeframe,
  settings,
  onCrosshair,
  onSourceChange,
}: {
  symbol: string;
  exchange: string;
  timeframe: TimeframeId;
  settings: ChartSettings;
  onCrosshair: (info: CrosshairPayload | null) => void;
  onSourceChange?: (source: string) => void;
}) {
  const priceContainerRef = useRef<HTMLDivElement>(null);
  const rsiContainerRef = useRef<HTMLDivElement>(null);
  const priceChartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);

  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const emaSeriesRefs = useRef<Map<number, ISeriesApi<"Line">>>(new Map());
  const stUpRef = useRef<ISeriesApi<"Line"> | null>(null);
  const stDownRef = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const candlesRef = useRef<Candle[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const applyChartTheme = useCallback(
    (chart: IChartApi) => {
      const c = chartColors();
      chart.applyOptions({
        layout: {
          background: { color: c.background },
          textColor: c.muted,
        },
        grid: {
          vertLines: { color: settings.showGrid ? c.grid : "transparent" },
          horzLines: { color: settings.showGrid ? c.grid : "transparent" },
        },
        crosshair: { mode: 1 },
        rightPriceScale: { borderColor: c.border, autoScale: settings.autoScale },
        timeScale: { borderColor: c.border, timeVisible: true, secondsVisible: false },
      });
    },
    [settings.autoScale, settings.showGrid],
  );

  const clearOverlaySeries = useCallback(() => {
    const chart = priceChartRef.current;
    if (!chart) return;
    emaSeriesRefs.current.forEach((s) => chart.removeSeries(s));
    emaSeriesRefs.current.clear();
    if (stUpRef.current) {
      chart.removeSeries(stUpRef.current);
      stUpRef.current = null;
    }
    if (stDownRef.current) {
      chart.removeSeries(stDownRef.current);
      stDownRef.current = null;
    }
  }, []);

  const applyIndicators = useCallback(
    (candles: Candle[]) => {
      const chart = priceChartRef.current;
      if (!chart) return;
      clearOverlaySeries();

      if (settings.ema.enabled) {
        settings.ema.periods.forEach((period) => {
          const line = chart.addLineSeries({
            color: EMA_COLORS[period] || "#888",
            lineWidth: 1,
            priceLineVisible: false,
            lastValueVisible: false,
          });
          line.setData(buildEmaData(candles, period));
          emaSeriesRefs.current.set(period, line);
        });
      }

      if (settings.supertrend.enabled) {
        const st = supertrendSeries(
          candles,
          settings.supertrend.period,
          settings.supertrend.multiplier,
        );
        const up: LineData[] = [];
        const down: LineData[] = [];
        st.forEach((p) => {
          if (p.trend === "up") up.push({ time: toUtc(p.time), value: p.value });
          else down.push({ time: toUtc(p.time), value: p.value });
        });
        const c = chartColors();
        stUpRef.current = chart.addLineSeries({
          color: c.profit,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        stDownRef.current = chart.addLineSeries({
          color: c.loss,
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        stUpRef.current.setData(up);
        stDownRef.current.setData(down);
      }

      if (settings.showVolume && volumeSeriesRef.current) {
        volumeSeriesRef.current.setData(buildVolumeData(candles));
      } else if (volumeSeriesRef.current) {
        volumeSeriesRef.current.setData([]);
      }

      const rsiChart = rsiChartRef.current;
      if (rsiChart && rsiSeriesRef.current && settings.rsi.enabled) {
        rsiSeriesRef.current.setData(buildRsiData(candles, settings.rsi.period));
      }
    },
    [clearOverlaySeries, settings],
  );

  const setMainSeriesData = useCallback(
    (candles: Candle[]) => {
      const candleData: CandlestickData[] = candles.map((c) => ({
        time: toUtc(c.time),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));
      const lineData: LineData[] = candles.map((c) => ({
        time: toUtc(c.time),
        value: c.close,
      }));

      if (settings.chartType === "line") {
        if (lineSeriesRef.current) lineSeriesRef.current.setData(lineData);
        if (candleSeriesRef.current) candleSeriesRef.current.setData([]);
      } else {
        if (candleSeriesRef.current) candleSeriesRef.current.setData(candleData);
        if (lineSeriesRef.current) lineSeriesRef.current.setData([]);
      }
    },
    [settings.chartType],
  );

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetchCandles(symbol, exchange, timeframe);
      candlesRef.current = res.candles;
      onSourceChange?.(res.source);
      setMainSeriesData(res.candles);
      applyIndicators(res.candles);
      priceChartRef.current?.timeScale().fitContent();
      rsiChartRef.current?.timeScale().fitContent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load chart data");
    } finally {
      setLoading(false);
    }
  }, [symbol, exchange, timeframe, applyIndicators, setMainSeriesData, onSourceChange]);

  // Init charts once
  useEffect(() => {
    if (!priceContainerRef.current) return;
    const c = chartColors();
    const priceChart = createChart(priceContainerRef.current, {
      width: priceContainerRef.current.clientWidth,
      height: Math.max(420, priceContainerRef.current.clientHeight || 520),
      layout: { background: { color: c.background }, textColor: c.muted },
      grid: {
        vertLines: { color: c.grid },
        horzLines: { color: c.grid },
      },
    });
    priceChartRef.current = priceChart;

    candleSeriesRef.current = priceChart.addCandlestickSeries({
      upColor: c.profit,
      downColor: c.loss,
      borderVisible: false,
      wickUpColor: c.profit,
      wickDownColor: c.loss,
    });
    lineSeriesRef.current = priceChart.addLineSeries({
      color: c.accent,
      lineWidth: 2,
      priceLineVisible: false,
      visible: false,
    });

    volumeSeriesRef.current = priceChart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    priceChart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    let rsiChart: IChartApi | null = null;
    if (rsiContainerRef.current) {
      rsiChart = createChart(rsiContainerRef.current, {
        width: rsiContainerRef.current.clientWidth,
        height: 100,
        layout: { background: { color: c.background }, textColor: c.muted },
        grid: {
          vertLines: { color: c.grid },
          horzLines: { color: c.grid },
        },
      });
      rsiChartRef.current = rsiChart;
      rsiSeriesRef.current = rsiChart.addLineSeries({
        color: "#8b5cf6",
        lineWidth: 1,
        priceLineVisible: false,
      });
    }

    const syncTime = () => {
      if (!rsiChart || !priceChart) return;
      const range = priceChart.timeScale().getVisibleLogicalRange();
      if (range) rsiChart.timeScale().setVisibleLogicalRange(range);
    };
    priceChart.timeScale().subscribeVisibleLogicalRangeChange(syncTime);

    priceChart.subscribeCrosshairMove((param) => {
      if (!param.time) {
        onCrosshair(null);
        return;
      }
      const cd = candleSeriesRef.current
        ? (param.seriesData.get(candleSeriesRef.current) as CandlestickData | undefined)
        : undefined;
      const ld = lineSeriesRef.current
        ? (param.seriesData.get(lineSeriesRef.current) as LineData | undefined)
        : undefined;
      const vol = volumeSeriesRef.current
        ? (param.seriesData.get(volumeSeriesRef.current) as HistogramData | undefined)
        : undefined;
      const close = cd?.close ?? ld?.value;
      if (close == null) {
        onCrosshair(null);
        return;
      }
      const open = cd?.open ?? close;
      const changePct = open ? ((close - open) / open) * 100 : 0;
      onCrosshair({
        o: cd?.open ?? close,
        h: cd?.high ?? close,
        l: cd?.low ?? close,
        c: close,
        vol: vol?.value ?? null,
        changePct,
      });
    });

    const resize = () => {
      if (priceContainerRef.current) {
        priceChart.applyOptions({
          width: priceContainerRef.current.clientWidth,
          height: Math.max(420, priceContainerRef.current.clientHeight || 520),
        });
      }
      if (rsiContainerRef.current && rsiChart) {
        rsiChart.applyOptions({ width: rsiContainerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", resize);

    return () => {
      window.removeEventListener("resize", resize);
      priceChart.remove();
      if (rsiChart) rsiChart.remove();
      priceChartRef.current = null;
      rsiChartRef.current = null;
    };
  }, [onCrosshair]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (priceChartRef.current) applyChartTheme(priceChartRef.current);
    if (rsiChartRef.current) applyChartTheme(rsiChartRef.current);
  }, [applyChartTheme]);

  useEffect(() => {
    if (candlesRef.current.length) applyIndicators(candlesRef.current);
  }, [settings, applyIndicators]);

  useEffect(() => {
    if (candlesRef.current.length) setMainSeriesData(candlesRef.current);
    if (lineSeriesRef.current) {
      lineSeriesRef.current.applyOptions({ visible: settings.chartType === "line" });
    }
    if (candleSeriesRef.current) {
      candleSeriesRef.current.applyOptions({ visible: settings.chartType === "candles" });
    }
  }, [settings.chartType, setMainSeriesData]);

  useEffect(() => {
    const sec = intervalSec(timeframe);
    const unsubTick = marketWebSocket.onTick((tick) => {
      if (tick.symbol !== symbol) return;
      const updated = updateCandleBucket(candlesRef.current, tick.time, tick.ltp, sec);
      const isNewBucket = updated.length !== candlesRef.current.length;
      candlesRef.current = updated;
      const last = updated[updated.length - 1];
      if (!last) return;

      if (settings.chartType === "line" && lineSeriesRef.current) {
        lineSeriesRef.current.update({ time: toUtc(last.time), value: last.close });
      } else if (candleSeriesRef.current) {
        candleSeriesRef.current.update({
          time: toUtc(last.time),
          open: last.open,
          high: last.high,
          low: last.low,
          close: last.close,
        });
      }

      if (settings.showVolume && volumeSeriesRef.current && last.volume != null) {
        const colors = chartColors();
        volumeSeriesRef.current.update({
          time: toUtc(last.time),
          value: last.volume,
          color: last.close >= last.open ? colors.profit + "55" : colors.loss + "55",
        });
      }

      if (isNewBucket) {
        applyIndicators(updated);
      }
    });

    marketWebSocket.subscribe(symbol, exchange);
    marketWebSocket.connect();

    return () => {
      unsubTick();
      marketWebSocket.unsubscribe(symbol);
    };
  }, [symbol, exchange, timeframe, settings.chartType, settings.showVolume, applyIndicators]);

  if (loading) return <ChartLoading />;
  if (error) return <ChartError message={error} onRetry={loadHistory} />;

  return (
    <div>
      <div ref={priceContainerRef} className="h-[min(68vh,640px)] min-h-[420px] w-full" />
      <div
        ref={rsiContainerRef}
        className={`w-full border-t border-[var(--line)] ${settings.rsi.enabled ? "" : "hidden"}`}
      />
    </div>
  );
}
