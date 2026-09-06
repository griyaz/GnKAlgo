"use client";

import { AppShell } from "@/components/AppShell";
import { OrderDetailsDrawer } from "@/components/orders/OrderDetailsDrawer";
import { OrdersTable } from "@/components/orders/OrdersTable";
import { QuickOrderPanel } from "@/components/orders/QuickOrderPanel";
import type { UnifiedOrder } from "@/lib/orders";
import {
  ErrorBanner,
  PageHeader,
  Panel,
  TabBar,
  TerminalInput,
  TerminalSelect,
} from "@/components/ui/terminal";
import { api } from "@/lib/api";
import {
  brokerToUnified,
  filterOrdersByTab,
  localToUnified,
  type LocalOrder,
} from "@/lib/orders";
import { useCallback, useEffect, useMemo, useState } from "react";

const TABS = [
  { id: "all", label: "All" },
  { id: "pending", label: "Pending" },
  { id: "executed", label: "Executed" },
  { id: "rejected", label: "Rejected" },
  { id: "cancelled", label: "Cancelled" },
];

export default function OrdersPage() {
  const [localOrders, setLocalOrders] = useState<LocalOrder[]>([]);
  const [brokerItems, setBrokerItems] = useState<Record<string, unknown>[]>([]);
  const [brokerConnected, setBrokerConnected] = useState(false);
  const [tab, setTab] = useState("all");
  const [sideFilter, setSideFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<UnifiedOrder | null>(null);
  const [repeatSymbol, setRepeatSymbol] = useState<string | undefined>();
  const [repeatSide, setRepeatSide] = useState<"BUY" | "SELL" | undefined>();

  const load = useCallback(async () => {
    setError("");
    try {
      const local = await api<LocalOrder[]>("/api/v1/orders/", {}, true);
      setLocalOrders(local);
      const brokerRes = await api<{
        connected: boolean;
        items: Record<string, unknown>[];
        error?: string;
      }>("/api/v1/portfolio/broker-orders?broker=dhan", {}, true);
      setBrokerConnected(brokerRes.connected);
      setBrokerItems(brokerRes.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load orders");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const unified = useMemo(() => {
    const local = localOrders.map(localToUnified);
    const broker = brokerItems.map((r, i) => brokerToUnified(r, i));
    const seen = new Set(local.map((o) => o.brokerOrderId).filter(Boolean));
    const merged = [...local];
    for (const b of broker) {
      if (!seen.has(b.brokerOrderId)) merged.push(b);
    }
    return merged.sort((a, b) => (b.orderTime || "").localeCompare(a.orderTime || ""));
  }, [localOrders, brokerItems]);

  const filtered = useMemo(() => {
    let rows = filterOrdersByTab(unified, tab);
    if (sideFilter !== "all") {
      rows = rows.filter((o) => o.side.toUpperCase() === sideFilter);
    }
    if (search.trim()) {
      const q = search.trim().toUpperCase();
      rows = rows.filter((o) => o.symbol.toUpperCase().includes(q));
    }
    return rows;
  }, [unified, tab, sideFilter, search]);

  return (
    <AppShell>
      <PageHeader
        back
        title="Orders"
        subtitle={brokerConnected ? "GnKAlgo + Dhan broker orders" : "Paper orders · Connect Dhan for live sync"}
        action={
          <button
            type="button"
            onClick={load}
            className="rounded border border-[var(--line)] px-2.5 py-1 text-[11px] hover:bg-[var(--panel-2)]"
          >
            Refresh
          </button>
        }
      />
      {error && <ErrorBanner message={error} />}

      <div className="grid gap-3 lg:grid-cols-[1fr_280px]">
        <Panel>
          <TabBar tabs={TABS} active={tab} onChange={setTab} />
          <div className="flex flex-wrap gap-2 p-2 border-b border-[var(--line)]">
            <TerminalInput
              placeholder="Search symbol"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-32"
            />
            <TerminalSelect value={sideFilter} onChange={(e) => setSideFilter(e.target.value)}>
              <option value="all">All sides</option>
              <option value="BUY">Buy</option>
              <option value="SELL">Sell</option>
            </TerminalSelect>
          </div>
          <OrdersTable
            orders={filtered}
            onView={setSelected}
            onRepeat={(o) => {
              setRepeatSymbol(o.symbol);
              setRepeatSide(o.side === "SELL" ? "SELL" : "BUY");
            }}
          />
        </Panel>
        <QuickOrderPanel
          defaultSymbol={repeatSymbol}
          defaultSide={repeatSide}
          onSuccess={load}
        />
      </div>

      <OrderDetailsDrawer order={selected} onClose={() => setSelected(null)} />
    </AppShell>
  );
}
