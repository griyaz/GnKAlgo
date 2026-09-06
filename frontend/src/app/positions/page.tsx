"use client";

import { AppShell } from "@/components/AppShell";
import { ExitPositionModal } from "@/components/positions/ExitPositionModal";
import { PositionSummary } from "@/components/positions/PositionSummary";
import { PositionsTable } from "@/components/positions/PositionsTable";
import {
  EmptyState,
  ErrorBanner,
  PageHeader,
  Panel,
  TabBar,
  TerminalInput,
} from "@/components/ui/terminal";
import { api } from "@/lib/api";
import { normalizePosition, type NormalizedPosition } from "@/lib/portfolio";
import { useCallback, useEffect, useMemo, useState } from "react";

const TABS = [
  { id: "open", label: "Open" },
  { id: "closed", label: "Closed" },
];

export default function PositionsPage() {
  const [raw, setRaw] = useState<Record<string, unknown>[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("open");
  const [search, setSearch] = useState("");
  const [exitTarget, setExitTarget] = useState<NormalizedPosition | null>(null);
  const [exitLoading, setExitLoading] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await api<{
        connected: boolean;
        items: Record<string, unknown>[];
        error?: string;
      }>("/api/v1/portfolio/positions?broker=dhan", {}, true);
      setConnected(res.connected);
      setRaw(res.items || []);
      if (res.error) setError(res.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load positions");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const positions = useMemo(
    () => raw.map((r, i) => normalizePosition(r, i)),
    [raw],
  );

  const filtered = useMemo(() => {
    let rows = positions;
    if (tab === "open") rows = rows.filter((p) => p.netQty !== 0);
    else rows = rows.filter((p) => p.netQty === 0);
    if (search.trim()) {
      const q = search.trim().toUpperCase();
      rows = rows.filter((p) => p.symbol.toUpperCase().includes(q));
    }
    return rows;
  }, [positions, tab, search]);

  async function confirmExit() {
    if (!exitTarget) return;
    setExitLoading(true);
    setError("");
    try {
      const side = exitTarget.netQty > 0 ? "SELL" : "BUY";
      const qty = Math.abs(exitTarget.netQty);
      await api("/api/v1/orders/", {
        method: "POST",
        body: JSON.stringify({
          symbol: exitTarget.symbol,
          exchange: "NSE",
          side,
          quantity: qty,
          order_type: "MARKET",
          product_type: exitTarget.product !== "—" ? exitTarget.product : "INTRADAY",
          paper_mode: true,
          broker: "paper",
        }),
      }, true);
      setExitTarget(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Exit order failed");
    } finally {
      setExitLoading(false);
    }
  }

  return (
    <AppShell>
      <PageHeader
        back
        title="Positions"
        subtitle={connected ? "Live from Dhan" : "Connect Dhan in Broker to sync positions"}
        action={
          <button type="button" onClick={load} className="rounded border border-[var(--line)] px-2.5 py-1 text-[11px]">
            Refresh
          </button>
        }
      />
      {error && <ErrorBanner message={error} />}
      <PositionSummary positions={positions.filter((p) => p.netQty !== 0)} />

      <Panel className="mt-3">
        <TabBar tabs={TABS} active={tab} onChange={setTab} />
        <div className="p-2 border-b border-[var(--line)]">
          <TerminalInput
            placeholder="Search symbol"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-40"
          />
        </div>
        {!connected ? (
          <EmptyState title="Broker not connected" detail="Connect Dhan on the Broker page to view live positions." />
        ) : filtered.length ? (
          <PositionsTable positions={filtered} onExit={setExitTarget} />
        ) : (
          <EmptyState title="No positions" detail={tab === "open" ? "No open positions." : "No closed positions."} />
        )}
      </Panel>

      <ExitPositionModal
        position={exitTarget}
        onClose={() => setExitTarget(null)}
        onConfirm={confirmExit}
        loading={exitLoading}
      />
    </AppShell>
  );
}
