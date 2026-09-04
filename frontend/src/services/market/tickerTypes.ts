// Shared types for the LiveMarketTicker WebSocket feed (/ws/market/ticker).

export type MarketStatusCode =
  | "PRE_OPEN"
  | "OPEN"
  | "CLOSED"
  | "HOLIDAY"
  | "UNKNOWN";

export type TickerItem = {
  symbol: string;
  display_name: string;
  exchange: string;
  provider: string;
  ltp: number | null;
  previous_close: number | null;
  change: number | null;
  change_percent: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  timestamp: string;
  market_status: MarketStatusCode;
  is_stale: boolean;
};

export type SnapshotMessage = {
  type: "snapshot";
  provider: string;
  market_status: MarketStatusCode;
  demo: boolean;
  stale: boolean;
  server_time: string;
  data: TickerItem[];
};

export type TickerUpdateMessage = {
  type: "ticker_update";
  provider: string;
  market_status: MarketStatusCode;
  server_time: string;
  demo: boolean;
  data: TickerItem[];
};

export type MarketStatusMessage = {
  type: "market_status";
  market_status: MarketStatusCode;
  label: string;
  server_time: string;
};

export type ProviderStatusMessage = {
  type: "provider_status";
  provider: string;
  connected: boolean;
  demo: boolean;
  server_time: string;
};

export type TickerMessage =
  | SnapshotMessage
  | TickerUpdateMessage
  | MarketStatusMessage
  | ProviderStatusMessage;

export type ConnectionState =
  | "CONNECTING"
  | "CONNECTED"
  | "RECONNECTING"
  | "DISCONNECTED"
  | "ERROR";
