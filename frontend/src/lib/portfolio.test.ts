import { describe, expect, it } from "vitest";

import {
  buildExitOrderPayload,
  exchangeFromSegment,
  isRejectedOrder,
  LIVE_ORDER_CONFIRMATION,
  type NormalizedPosition,
} from "@/lib/portfolio";

function position(overrides: Partial<NormalizedPosition> = {}): NormalizedPosition {
  return {
    id: "pos-1",
    symbol: "RELIANCE",
    exchange: "NSE_EQ",
    product: "INTRADAY",
    netQty: 10,
    buyQty: 10,
    buyAvg: 1400,
    sellQty: 0,
    sellAvg: null,
    ltp: 1410,
    invested: 14000,
    realizedPnl: 0,
    unrealizedPnl: 100,
    totalPnl: 100,
    pnlPct: 0.71,
    raw: {},
    ...overrides,
  };
}

describe("exchangeFromSegment", () => {
  it("maps Dhan NSE segments to NSE", () => {
    expect(exchangeFromSegment("NSE_EQ")).toBe("NSE");
    expect(exchangeFromSegment("NSE_FNO")).toBe("NSE");
    expect(exchangeFromSegment("NSE")).toBe("NSE");
  });

  it("maps Dhan BSE segments to BSE", () => {
    expect(exchangeFromSegment("BSE_EQ")).toBe("BSE");
    expect(exchangeFromSegment("BSE")).toBe("BSE");
  });

  it("defaults missing segments to NSE", () => {
    expect(exchangeFromSegment(undefined)).toBe("NSE");
  });
});

describe("buildExitOrderPayload", () => {
  it("sends a live Dhan market SELL to flatten a long position", () => {
    expect(buildExitOrderPayload(position())).toEqual({
      symbol: "RELIANCE",
      exchange: "NSE",
      side: "SELL",
      quantity: 10,
      order_type: "MARKET",
      product_type: "INTRADAY",
      paper_mode: false,
      broker: "dhan",
      live_confirmation: LIVE_ORDER_CONFIRMATION,
    });
  });

  it("sends a live Dhan market BUY to cover a short position", () => {
    const payload = buildExitOrderPayload(
      position({ symbol: "TCS", exchange: "BSE_EQ", product: "CNC", netQty: -25 }),
    );
    expect(payload.side).toBe("BUY");
    expect(payload.quantity).toBe(25);
    expect(payload.exchange).toBe("BSE");
    expect(payload.product_type).toBe("CNC");
    expect(payload.paper_mode).toBe(false);
    expect(payload.broker).toBe("dhan");
  });

  it("does not fall back to paper mode or omit live confirmation", () => {
    const payload = buildExitOrderPayload(position());
    expect(payload.paper_mode).toBe(false);
    expect(payload.broker).not.toBe("paper");
    expect(payload.live_confirmation).toBe("CONFIRM LIVE ORDER");
  });

  it("rejects a flat position", () => {
    expect(() => buildExitOrderPayload(position({ netQty: 0 }))).toThrow("Nothing to exit");
  });
});

describe("isRejectedOrder", () => {
  it("treats broker and local rejects as failures", () => {
    expect(isRejectedOrder("REJECTED")).toBe(true);
    expect(isRejectedOrder("rejected")).toBe(true);
    expect(isRejectedOrder("TRADED")).toBe(false);
    expect(isRejectedOrder("PAPER_FILLED")).toBe(false);
  });
});
