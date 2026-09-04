import { describe, expect, it } from "vitest";

import {
  changeDirection,
  directionArrow,
  formatChange,
  formatNumber,
  initialTickerState,
  orderedIndexes,
  tickerReducer,
} from "@/hooks/useMarketTicker";
import type {
  SnapshotMessage,
  TickerItem,
  TickerUpdateMessage,
} from "@/services/market/tickerTypes";

function item(overrides: Partial<TickerItem>): TickerItem {
  return {
    symbol: "NIFTY50",
    display_name: "NIFTY 50",
    exchange: "NSE",
    provider: "MOCK",
    ltp: 25123.5,
    previous_close: 24990.3,
    change: 133.2,
    change_percent: 0.53,
    open: null,
    high: null,
    low: null,
    timestamp: "2026-09-04T09:20:00+00:00",
    market_status: "OPEN",
    is_stale: false,
    ...overrides,
  };
}

// 10. Frontend update reducer / state ---------------------------------------
describe("tickerReducer", () => {
  it("loads a snapshot and preserves order", () => {
    const snap: SnapshotMessage = {
      type: "snapshot",
      provider: "FYERS",
      market_status: "OPEN",
      demo: false,
      stale: false,
      server_time: "2026-09-04T09:20:00+00:00",
      data: [item({ symbol: "NIFTY50" }), item({ symbol: "BANKNIFTY", display_name: "NIFTY BANK" })],
    };
    const state = tickerReducer(initialTickerState, snap);
    expect(orderedIndexes(state).map((i) => i.symbol)).toEqual(["NIFTY50", "BANKNIFTY"]);
    expect(state.provider).toBe("FYERS");
    expect(state.marketStatus).toBe("OPEN");
  });

  it("merges ticker_update by symbol without reordering", () => {
    const snap: SnapshotMessage = {
      type: "snapshot",
      provider: "FYERS",
      market_status: "OPEN",
      demo: false,
      stale: false,
      server_time: "t0",
      data: [item({ symbol: "NIFTY50" }), item({ symbol: "BANKNIFTY" })],
    };
    let state = tickerReducer(initialTickerState, snap);
    const update: TickerUpdateMessage = {
      type: "ticker_update",
      provider: "FYERS",
      market_status: "OPEN",
      demo: false,
      server_time: "t1",
      data: [item({ symbol: "NIFTY50", ltp: 25200, change: 209.7, change_percent: 0.84 })],
    };
    state = tickerReducer(state, update);
    expect(orderedIndexes(state).map((i) => i.symbol)).toEqual(["NIFTY50", "BANKNIFTY"]);
    expect(state.bySymbol.NIFTY50.ltp).toBe(25200);
    expect(state.lastUpdated).toBe("t1");
  });

  it("marks stale from a stale tick and clears on fresh data", () => {
    const base = tickerReducer(initialTickerState, {
      type: "snapshot",
      provider: "FYERS",
      market_status: "OPEN",
      demo: false,
      stale: false,
      server_time: "t0",
      data: [item({})],
    });
    const stale = tickerReducer(base, {
      type: "ticker_update",
      provider: "FYERS",
      market_status: "OPEN",
      demo: false,
      server_time: "t1",
      data: [item({ is_stale: true })],
    });
    expect(stale.stale).toBe(true);
    const fresh = tickerReducer(stale, {
      type: "ticker_update",
      provider: "FYERS",
      market_status: "OPEN",
      demo: false,
      server_time: "t2",
      data: [item({ is_stale: false })],
    });
    expect(fresh.stale).toBe(false);
  });

  it("updates market_status and provider messages", () => {
    let state = tickerReducer(initialTickerState, {
      type: "market_status",
      market_status: "CLOSED",
      label: "Market Closed",
      server_time: "t",
    });
    expect(state.marketStatus).toBe("CLOSED");
    state = tickerReducer(state, {
      type: "provider_status",
      provider: "DHAN",
      connected: true,
      demo: false,
      server_time: "t",
    });
    expect(state.provider).toBe("DHAN");
  });
});

// 11 + 12. Positive / negative change rendering (accessible label) ----------
describe("formatChange", () => {
  it("renders a positive change with an up arrow and + sign", () => {
    const r = formatChange(133.2, 0.53);
    expect(r.direction).toBe("up");
    expect(r.arrow).toBe("▲");
    expect(r.text).toBe("+133.20 (+0.53%)");
  });

  it("renders a negative change with a down arrow and - sign", () => {
    const r = formatChange(-62.1, -0.11);
    expect(r.direction).toBe("down");
    expect(r.arrow).toBe("▼");
    expect(r.text).toBe("-62.10 (-0.11%)");
  });

  it("renders zero without an arrow", () => {
    const r = formatChange(0, 0);
    expect(r.direction).toBe("flat");
    expect(r.arrow).toBe("");
    expect(r.text).toBe("0.00 (0.00%)");
  });

  it("handles missing values", () => {
    expect(formatChange(null, null).text).toBe("—");
  });
});

describe("helpers", () => {
  it("changeDirection + directionArrow", () => {
    expect(directionArrow(changeDirection(5))).toBe("▲");
    expect(directionArrow(changeDirection(-5))).toBe("▼");
    expect(directionArrow(changeDirection(0))).toBe("");
    expect(directionArrow(changeDirection(null))).toBe("");
  });

  it("formatNumber groups and handles null", () => {
    expect(formatNumber(25123.5)).toBe("25,123.50");
    expect(formatNumber(null)).toBe("—");
  });
});
