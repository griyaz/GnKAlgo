"use client";

import { pickNum, pickStr } from "@/lib/format";

export type NormalizedPosition = {
  id: string;
  symbol: string;
  exchange: string;
  product: string;
  netQty: number;
  buyQty: number;
  buyAvg: number | null;
  sellQty: number;
  sellAvg: number | null;
  ltp: number | null;
  invested: number | null;
  realizedPnl: number;
  unrealizedPnl: number;
  totalPnl: number;
  pnlPct: number | null;
  raw: Record<string, unknown>;
};

export function normalizePosition(raw: Record<string, unknown>, index: number): NormalizedPosition {
  const symbol = pickStr(raw, ["tradingSymbol", "symbol", "securityId"], `POS-${index}`);
  const netQty = pickNum(raw, ["netQty", "netQuantity", "quantity"]) ?? 0;
  const buyQty = pickNum(raw, ["buyQty", "buyQuantity"]) ?? 0;
  const sellQty = pickNum(raw, ["sellQty", "sellQuantity"]) ?? 0;
  const buyAvg = pickNum(raw, ["buyAvg", "buyAverage", "averageBuyPrice"]);
  const sellAvg = pickNum(raw, ["sellAvg", "sellAverage", "averageSellPrice"]);
  const ltp = pickNum(raw, ["ltp", "lastPrice", "lastTradedPrice"]);
  const realizedPnl = pickNum(raw, ["realizedProfit", "realizedPnl", "realized_profit"]) ?? 0;
  const unrealizedPnl = pickNum(raw, ["unrealizedProfit", "unrealizedPnl", "unrealized_profit"]) ?? 0;
  const totalPnl = realizedPnl + unrealizedPnl;
  const invested = buyAvg && buyQty ? buyAvg * buyQty : null;
  const pnlPct = invested && invested > 0 ? (totalPnl / invested) * 100 : null;

  return {
    id: pickStr(raw, ["positionId", "id"], `${symbol}-${index}`),
    symbol,
    exchange: pickStr(raw, ["exchangeSegment", "exchange"], "NSE"),
    product: pickStr(raw, ["productType", "product"], "—"),
    netQty,
    buyQty,
    buyAvg,
    sellQty,
    sellAvg,
    ltp,
    invested,
    realizedPnl,
    unrealizedPnl,
    totalPnl,
    pnlPct,
    raw,
  };
}

export const LIVE_ORDER_CONFIRMATION = "CONFIRM LIVE ORDER";

/** Map Dhan exchangeSegment values (NSE_EQ, BSE_EQ, …) to PlaceOrderRequest.exchange. */
export function exchangeFromSegment(segment: string | undefined): "NSE" | "BSE" {
  const value = (segment || "NSE").toUpperCase();
  if (value.startsWith("BSE")) return "BSE";
  return "NSE";
}

export function isRejectedOrder(status: string | undefined): boolean {
  return (status || "").toUpperCase().includes("REJECT");
}

/** Live Dhan MARKET ticket that actually closes a broker position. */
export function buildExitOrderPayload(position: NormalizedPosition) {
  const quantity = Math.abs(position.netQty);
  if (quantity <= 0) {
    throw new Error("Nothing to exit");
  }
  return {
    symbol: position.symbol,
    exchange: exchangeFromSegment(position.exchange),
    side: position.netQty > 0 ? ("SELL" as const) : ("BUY" as const),
    quantity,
    order_type: "MARKET" as const,
    product_type: position.product !== "—" ? position.product : "INTRADAY",
    paper_mode: false,
    broker: "dhan" as const,
    live_confirmation: LIVE_ORDER_CONFIRMATION,
  };
}
