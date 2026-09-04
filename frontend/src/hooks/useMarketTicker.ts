"use client";

import { useEffect, useMemo, useReducer } from "react";

import { api } from "@/lib/api";
import { marketTickerSocket } from "@/services/marketTickerSocket";
import type {
  ConnectionState,
  MarketStatusCode,
  SnapshotMessage,
  TickerItem,
  TickerMessage,
} from "@/services/market/tickerTypes";

// ---------------------------------------------------------------------------
// Pure state + reducer (exported for tests — Phase 20 items 10-12)
// ---------------------------------------------------------------------------
export type TickerState = {
  order: string[];
  bySymbol: Record<string, TickerItem>;
  marketStatus: MarketStatusCode;
  provider: string;
  stale: boolean;
  demo: boolean;
  lastUpdated: string | null;
};

export const initialTickerState: TickerState = {
  order: [],
  bySymbol: {},
  marketStatus: "UNKNOWN",
  provider: "NONE",
  stale: false,
  demo: false,
  lastUpdated: null,
};

function applyItems(
  state: TickerState,
  items: TickerItem[],
  keepOrder: boolean,
): TickerState {
  const bySymbol = { ...state.bySymbol };
  const order = keepOrder ? [...state.order] : [];
  for (const item of items) {
    bySymbol[item.symbol] = { ...bySymbol[item.symbol], ...item };
    if (!order.includes(item.symbol)) order.push(item.symbol);
  }
  return { ...state, order, bySymbol };
}

export function tickerReducer(
  state: TickerState,
  msg: TickerMessage,
): TickerState {
  switch (msg.type) {
    case "snapshot": {
      const next = applyItems(
        { ...state, order: [], bySymbol: {} },
        msg.data,
        false,
      );
      return {
        ...next,
        provider: msg.provider,
        marketStatus: msg.market_status,
        demo: msg.demo,
        stale: msg.stale,
        lastUpdated: msg.server_time,
      };
    }
    case "ticker_update": {
      const next = applyItems(state, msg.data, true);
      const stale = msg.data.some((d) => d.is_stale);
      return {
        ...next,
        provider: msg.provider,
        marketStatus: msg.market_status,
        demo: msg.demo,
        stale,
        lastUpdated: msg.server_time,
      };
    }
    case "market_status":
      return { ...state, marketStatus: msg.market_status };
    case "provider_status":
      return { ...state, provider: msg.provider, demo: msg.demo };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Formatting helpers (pure — exported for tests + accessibility)
// ---------------------------------------------------------------------------
export type ChangeDirection = "up" | "down" | "flat";

export function changeDirection(change: number | null | undefined): ChangeDirection {
  if (change == null || change === 0) return "flat";
  return change > 0 ? "up" : "down";
}

export function directionArrow(direction: ChangeDirection): string {
  if (direction === "up") return "▲";
  if (direction === "down") return "▼";
  return "";
}

export function formatNumber(n: number | null | undefined, decimals = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Accessible change label: arrow + sign + value + percent (never color-only). */
export function formatChange(
  change: number | null | undefined,
  changePercent: number | null | undefined,
): { direction: ChangeDirection; arrow: string; text: string } {
  const direction = changeDirection(change);
  const arrow = directionArrow(direction);
  if (change == null || changePercent == null) {
    return { direction: "flat", arrow: "", text: "—" };
  }
  const sign = change > 0 ? "+" : "";
  const text = `${sign}${formatNumber(change)} (${sign}${formatNumber(changePercent)}%)`;
  return { direction, arrow, text };
}

export function orderedIndexes(state: TickerState): TickerItem[] {
  return state.order.map((s) => state.bySymbol[s]).filter(Boolean);
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
export type UseMarketTicker = {
  indexes: TickerItem[];
  marketStatus: MarketStatusCode;
  provider: string;
  connected: boolean;
  connectionState: ConnectionState;
  lastUpdated: string | null;
  stale: boolean;
  demo: boolean;
};

type HookState = {
  ticker: TickerState;
  connectionState: ConnectionState;
};

type HookAction =
  | { kind: "message"; msg: TickerMessage }
  | { kind: "state"; state: ConnectionState };

function hookReducer(state: HookState, action: HookAction): HookState {
  if (action.kind === "message") {
    return { ...state, ticker: tickerReducer(state.ticker, action.msg) };
  }
  return { ...state, connectionState: action.state };
}

export function useMarketTicker(): UseMarketTicker {
  const [state, dispatch] = useReducer(hookReducer, {
    ticker: initialTickerState,
    connectionState: "DISCONNECTED",
  });

  useEffect(() => {
    let cancelled = false;

    // 1. Initial snapshot via REST for an instant first paint.
    api<SnapshotMessage>("/api/v1/market/ticker")
      .then((snap) => {
        if (!cancelled && snap && snap.type === "snapshot") {
          dispatch({ kind: "message", msg: snap });
        }
      })
      .catch(() => undefined);

    // 2. Live updates via the single shared WebSocket.
    const offMsg = marketTickerSocket.onMessage((msg) =>
      dispatch({ kind: "message", msg }),
    );
    const offState = marketTickerSocket.onState((s) =>
      dispatch({ kind: "state", state: s }),
    );
    const releaseSocket = marketTickerSocket.acquire();

    return () => {
      cancelled = true;
      offMsg();
      offState();
      releaseSocket();
    };
  }, []);

  const indexes = useMemo(() => orderedIndexes(state.ticker), [state.ticker]);

  return {
    indexes,
    marketStatus: state.ticker.marketStatus,
    provider: state.ticker.provider,
    connected: state.connectionState === "CONNECTED",
    connectionState: state.connectionState,
    lastUpdated: state.ticker.lastUpdated,
    stale: state.ticker.stale,
    demo: state.ticker.demo,
  };
}
