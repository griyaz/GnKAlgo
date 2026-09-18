"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { ErrorBanner, TerminalInput, TerminalSelect } from "@/components/ui/terminal";

type QuickOrderPanelProps = {
  defaultSymbol?: string;
  defaultSide?: "BUY" | "SELL";
  onSuccess?: () => void;
  onClose?: () => void;
};

export function QuickOrderPanel({
  defaultSymbol = "RELIANCE",
  defaultSide = "BUY",
  onSuccess,
  onClose,
}: QuickOrderPanelProps) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [exchange, setExchange] = useState("NSE");
  const [side, setSide] = useState<"BUY" | "SELL">(defaultSide);
  const [quantity, setQuantity] = useState(1);
  const [orderType, setOrderType] = useState("MARKET");
  const [productType, setProductType] = useState("INTRADAY");
  const [price, setPrice] = useState("");
  const [triggerPrice, setTriggerPrice] = useState("");
  const [paperMode, setPaperMode] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [liveConfirmation, setLiveConfirmation] = useState("");

  useEffect(() => {
    if (defaultSymbol) setSymbol(defaultSymbol);
    if (defaultSide) setSide(defaultSide);
  }, [defaultSymbol, defaultSide]);

  async function submit() {
    setLoading(true);
    setError("");
    try {
      const trigger = triggerPrice.trim() ? Number(triggerPrice) : null;
      await api("/api/v1/orders/", {
        method: "POST",
        body: JSON.stringify({
          symbol: symbol.toUpperCase(),
          exchange,
          side,
          quantity: Number(quantity),
          order_type: orderType,
          product_type: productType,
          price: price ? Number(price) : null,
          trigger_price: trigger && trigger > 0 ? trigger : null,
          paper_mode: paperMode,
          broker: paperMode ? "paper" : "dhan",
          live_confirmation: paperMode ? null : liveConfirmation,
        }),
      }, true);
      setConfirm(false);
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Order failed");
    } finally {
      setLoading(false);
    }
  }

  const estLabel = `${side} ${quantity} × ${symbol} · ${
    triggerPrice ? `stop ${orderType} @ ${triggerPrice}` : orderType
  } · ${productType}${paperMode ? " · Paper" : " · Live"}`;

  return (
    <div className="rounded border border-[var(--line)] bg-[var(--panel)] p-3">
      <div className="flex items-center justify-between gap-2 mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-white">Quick Order</h3>
        {onClose && (
          <button type="button" onClick={onClose} className="text-[var(--muted)] hover:text-white text-xs">
            ✕
          </button>
        )}
      </div>
      {error && <ErrorBanner message={error} />}
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <TerminalInput value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Symbol" />
        <TerminalSelect value={exchange} onChange={(e) => setExchange(e.target.value)}>
          <option value="NSE">NSE</option>
          <option value="BSE">BSE</option>
        </TerminalSelect>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => setSide("BUY")}
            className={`flex-1 rounded py-1.5 text-xs font-semibold ${side === "BUY" ? "bg-[var(--profit)] text-black" : "border border-[var(--line)] text-[var(--muted)]"}`}
          >
            BUY
          </button>
          <button
            type="button"
            onClick={() => setSide("SELL")}
            className={`flex-1 rounded py-1.5 text-xs font-semibold ${side === "SELL" ? "bg-[var(--loss)] text-white" : "border border-[var(--line)] text-[var(--muted)]"}`}
          >
            SELL
          </button>
        </div>
        <TerminalInput type="number" min={1} value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} placeholder="Qty" />
        <TerminalSelect value={orderType} onChange={(e) => setOrderType(e.target.value)}>
          <option value="MARKET">MARKET</option>
          <option value="LIMIT">LIMIT</option>
        </TerminalSelect>
        <TerminalSelect value={productType} onChange={(e) => setProductType(e.target.value)}>
          <option value="INTRADAY">INTRADAY</option>
          <option value="CNC">CNC / DELIVERY</option>
          <option value="MARGIN">MARGIN</option>
        </TerminalSelect>
        <TerminalInput value={price} onChange={(e) => setPrice(e.target.value)} placeholder="Price (limit)" />
        <TerminalInput value={triggerPrice} onChange={(e) => setTriggerPrice(e.target.value)} placeholder="Trigger price" />
        <label className="flex items-center gap-2 text-xs text-[var(--muted)] sm:col-span-2">
          <input type="checkbox" checked={paperMode} onChange={(e) => setPaperMode(e.target.checked)} />
          Paper mode (no live broker call)
        </label>
      </div>
      <p className="mt-2 text-[11px] text-[var(--muted)]">{estLabel}</p>
      {!confirm ? (
        <button
          type="button"
          onClick={() => setConfirm(true)}
          className={`mt-3 w-full rounded py-2 text-xs font-semibold ${
            side === "BUY" ? "bg-[var(--profit)] text-black" : "bg-[var(--loss)] text-white"
          }`}
        >
          Review {side}
        </button>
      ) : (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-white">Confirm: {estLabel}</p>
          {!paperMode && <TerminalInput value={liveConfirmation} onChange={(e) => setLiveConfirmation(e.target.value)} placeholder="Type CONFIRM LIVE ORDER" />}
          <div className="flex gap-2">
            <button type="button" onClick={() => setConfirm(false)} className="flex-1 rounded border border-[var(--line)] py-2 text-xs">
              Cancel
            </button>
            <button
              type="button"
              disabled={loading || (!paperMode && liveConfirmation !== "CONFIRM LIVE ORDER")}
              onClick={submit}
              className={`flex-1 rounded py-2 text-xs font-semibold disabled:opacity-50 ${
                side === "BUY" ? "bg-[var(--profit)] text-black" : "bg-[var(--loss)] text-white"
              }`}
            >
              {loading ? "Submitting…" : `Place ${side}`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
