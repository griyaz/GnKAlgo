import { api } from "@/lib/api";
import type { Candle } from "@/lib/indicators";

export type Instrument = {
  symbol: string;
  display_name: string;
  exchange: string;
  segment: string;
  security_id: string;
  instrument_token: string;
  exchange_segment?: string;
  instrument_type?: string;
  expiry?: string | null;
  strike?: number | null;
  option_type?: string | null;
  underlying_symbol?: string | null;
  lot_size?: number | null;
  trading_symbol?: string | null;
};

export type InstrumentSearchResult = {
  items: Instrument[];
  total: number;
  source: string;
};

export type Quote = {
  symbol: string;
  display_name: string;
  exchange: string;
  ltp: number;
  change: number;
  change_pct: number;
  security_id: string;
  source?: string;
};

export type MarketSession = {
  status: "open" | "closed" | "pre_open";
  label: string;
  session: string;
};

export async function fetchMarketSession(): Promise<MarketSession> {
  return api<MarketSession>("/api/v1/market/status", {}, true);
}

export async function searchInstruments(
  q: string,
  options?: { limit?: number; exchange?: string; segment?: string },
): Promise<Instrument[]> {
  const params = new URLSearchParams({ q });
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.exchange) params.set("exchange", options.exchange);
  if (options?.segment) params.set("segment", options.segment);
  const res = await api<InstrumentSearchResult>(
    `/api/v1/market/instruments/search?${params}`,
    {},
    true,
  );
  return res.items;
}

export async function fetchInstrument(symbol: string, exchange = "NSE"): Promise<Instrument> {
  const params = new URLSearchParams({ exchange });
  return api<Instrument>(
    `/api/v1/market/instruments/${encodeURIComponent(symbol)}?${params}`,
    {},
    true,
  );
}

export async function fetchCandles(
  symbol: string,
  exchange: string,
  interval: string,
): Promise<{ candles: Candle[]; source: string }> {
  const params = new URLSearchParams({ symbol, exchange, interval });
  const res = await api<{ candles: Candle[]; source: string }>(
    `/api/v1/market/candles?${params}`,
    {},
    true,
  );
  return res;
}

export async function fetchQuote(symbol: string, exchange: string): Promise<Quote> {
  const params = new URLSearchParams({ symbol, exchange });
  return api<Quote>(`/api/v1/market/quote?${params}`, {}, true);
}

export async function fetchBrokerStatus(): Promise<{
  status: string;
  connected?: boolean;
}> {
  const res = await api<{ status: string; connected?: boolean }>(
    "/api/v1/portfolio/broker-status?broker=dhan",
    {},
    true,
  );
  return { status: res.status, connected: res.status === "connected" };
}
