"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { BackButton } from "@/components/ui/BackButton";
import { ChartHeader } from "@/components/charts/ChartHeader";
import { ChartLegend } from "@/components/charts/ChartLegend";
import { ChartSettingsPanel } from "@/components/charts/ChartSettingsPanel";
import { IndicatorToolbar } from "@/components/charts/IndicatorToolbar";
import { SymbolSearch } from "@/components/charts/SymbolSearch";
import { TimeframeSelector } from "@/components/charts/TimeframeSelector";
import { TradingChart, type CrosshairPayload } from "@/components/charts/TradingChart";
import { Panel } from "@/components/ui/terminal";
import {
  DEFAULT_CHART_SETTINGS,
  loadChartSettings,
  saveChartSettings,
  type ChartSettings,
  type TimeframeId,
} from "@/lib/chartSettings";
import {
  fetchBrokerStatus,
  fetchQuote,
  type Instrument,
  type Quote,
} from "@/services/chartDataService";
import { marketDataService } from "@/services/market/marketDataService";
import { marketWebSocket } from "@/services/marketWebSocket";

const DEFAULT_INSTRUMENT: Instrument = {
  symbol: "NIFTY50",
  display_name: "Nifty 50",
  exchange: "NSE",
  segment: "INDEX",
  security_id: "13",
  instrument_token: "13",
};

export default function ChartsPage() {
  const [instrument, setInstrument] = useState<Instrument>(DEFAULT_INSTRUMENT);
  const [timeframe, setTimeframe] = useState<TimeframeId>("5m");
  const [settings, setSettings] = useState<ChartSettings>(DEFAULT_CHART_SETTINGS);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [brokerConnected, setBrokerConnected] = useState(true);
  const [brokerStatus, setBrokerStatus] = useState("");
  const [wsStatus, setWsStatus] = useState("DISCONNECTED");
  const [crosshair, setCrosshair] = useState<CrosshairPayload | null>(null);
  const [dataSource, setDataSource] = useState("");
  const [fullscreen, setFullscreen] = useState(false);
  const [marketLabel, setMarketLabel] = useState("Market");
  const [marketOpen, setMarketOpen] = useState(false);

  const fsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSettings(loadChartSettings());
  }, []);

  const updateSettings = useCallback((s: ChartSettings) => {
    setSettings(s);
    saveChartSettings(s);
  }, []);

  const refreshQuote = useCallback(async () => {
    try {
      const q = await fetchQuote(instrument.symbol, instrument.exchange);
      setQuote(q);
    } catch {
      setQuote({
        symbol: instrument.symbol,
        display_name: instrument.display_name,
        exchange: instrument.exchange,
        ltp: 0,
        change: 0,
        change_pct: 0,
        security_id: instrument.security_id,
      });
    }
  }, [instrument]);

  useEffect(() => {
    refreshQuote();
    const t = setInterval(refreshQuote, 15000);
    return () => clearInterval(t);
  }, [refreshQuote]);

  useEffect(() => {
    fetchBrokerStatus()
      .then((r) => {
        setBrokerConnected(r.connected ?? r.status === "connected");
        setBrokerStatus(r.status);
      })
      .catch(() => setBrokerConnected(false));
  }, []);

  useEffect(() => {
    const refresh = () => {
      const st = marketDataService.getStatus();
      if (st) {
        setMarketLabel(st.label);
        setMarketOpen(st.status === "open");
      }
    };
    refresh();
    marketDataService.connect(30000);
    const unsub = marketDataService.subscribe(refresh);
    return () => {
      unsub();
      marketDataService.disconnect();
    };
  }, []);

  useEffect(() => {
    setWsStatus(marketWebSocket.getStatus());
    const unsub = marketWebSocket.onStatus(setWsStatus);
    marketWebSocket.connect();
    return () => unsub();
  }, []);

  const enterFullscreen = async () => {
    if (!fsRef.current) return;
    try {
      await fsRef.current.requestFullscreen();
      setFullscreen(true);
    } catch {
      setFullscreen(true);
    }
  };

  useEffect(() => {
    const onFs = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  const handleSelect = (inst: Instrument) => {
    setInstrument(inst);
    setCrosshair(null);
  };

  const chartBlock = (
  <>
      <ChartHeader
        quote={quote}
        displayName={instrument.display_name}
        marketLabel={marketLabel}
        marketOpen={marketOpen}
        wsStatus={wsStatus}
        crosshair={crosshair}
        dataSource={dataSource}
      />
      <ChartLegend settings={settings} />
      <div className="flex flex-wrap items-end gap-3 border-b border-[var(--line)] px-3 py-2">
        <SymbolSearch
          symbol={instrument.symbol}
          exchange={instrument.exchange}
          onSelect={handleSelect}
        />
        <TimeframeSelector value={timeframe} onChange={setTimeframe} />
        <IndicatorToolbar settings={settings} onChange={updateSettings} />
        <ChartSettingsPanel settings={settings} onChange={updateSettings} />
        <div>
          <span className="mb-1 block text-[10px] uppercase text-[var(--muted)]">View</span>
          <button
            type="button"
            onClick={enterFullscreen}
            className="rounded border border-[var(--line)] px-3 py-1.5 text-[10px] font-medium text-white hover:border-[var(--accent)]"
          >
            Fullscreen
          </button>
        </div>
      </div>
      {!brokerConnected && (
        <div className="mx-3 mt-2 flex flex-wrap items-center justify-between gap-2 rounded border border-[var(--warning)]/30 bg-[var(--warning)]/10 px-3 py-2 text-xs">
          <span className="text-[var(--warning)]">
            Connect Dhan to access live market data. Status: {brokerStatus || "disconnected"}
          </span>
          <Link href="/broker" className="text-[var(--accent)] hover:underline">
            Connect Broker
          </Link>
        </div>
      )}
      <TradingChart
        symbol={instrument.symbol}
        exchange={instrument.exchange}
        timeframe={timeframe}
        settings={settings}
        onCrosshair={setCrosshair}
        onSourceChange={setDataSource}
      />
    </>
  );

  return (
    <AppShell>
      {!fullscreen && <BackButton className="mb-2" />}
      <div ref={fsRef} className={fullscreen ? "bg-[var(--panel)]" : ""}>
        <Panel className="overflow-hidden">
          {chartBlock}
        </Panel>
      </div>
    </AppShell>
  );
}
