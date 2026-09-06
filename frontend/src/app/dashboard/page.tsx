"use client";

import { AppShell } from "@/components/AppShell";
import { AISignalTable } from "@/components/ai/AISignalTable";
import { HoldingsTable } from "@/components/holdings/HoldingsTable";
import { OrdersTable } from "@/components/orders/OrdersTable";
import { PositionsTable } from "@/components/positions/PositionsTable";
import {
  ErrorBanner,
  PageHeader,
  Panel,
  SummaryTile,
} from "@/components/ui/terminal";
import { api } from "@/lib/api";
import { fmtINR } from "@/lib/format";
import { normalizeHolding } from "@/lib/holdings";
import { localToUnified, type LocalOrder } from "@/lib/orders";
import { normalizePosition } from "@/lib/portfolio";
import { fetchProfile } from "@/services/profileService";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

type Summary = {
  user: string;
  orders_count: number;
  active_strategies: number;
  signals_count: number;
  broker_status: Record<string, string>;
  recent_signals: { symbol: string; action: string; confidence: number }[];
  recent_orders: { symbol: string; side: string; status: string; quantity: number }[];
  subscription?: { active: boolean; plan_code?: string; expires_at?: string };
};

type Signal = {
  id: string;
  symbol: string;
  action: string;
  confidence: number;
  price?: number | null;
  created_at: string;
};

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [funds, setFunds] = useState<Record<string, unknown> | null>(null);
  const [positions, setPositions] = useState<Record<string, unknown>[]>([]);
  const [holdings, setHoldings] = useState<Record<string, unknown>[]>([]);
  const [orders, setOrders] = useState<LocalOrder[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [error, setError] = useState("");

  const [displayName, setDisplayName] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [dash, fundsRes, posRes, holdRes, ordRes, sigRes, profile] = await Promise.all([
        api<Summary>("/api/v1/dashboard/summary", {}, true),
        api<{ data: Record<string, unknown> | null }>("/api/v1/portfolio/funds?broker=dhan", {}, true),
        api<{ items: Record<string, unknown>[] }>("/api/v1/portfolio/positions?broker=dhan", {}, true),
        api<{ items: Record<string, unknown>[] }>("/api/v1/portfolio/holdings?broker=dhan", {}, true),
        api<LocalOrder[]>("/api/v1/orders/", {}, true),
        api<Signal[]>("/api/v1/signals/", {}, true),
        fetchProfile().catch(() => null),
      ]);
      setSummary(dash);
      setFunds(fundsRes.data);
      setPositions(posRes.items || []);
      setHoldings(holdRes.items || []);
      setOrders(ordRes.slice(0, 5));
      setSignals(sigRes.slice(0, 5));
      if (profile?.display_name) setDisplayName(profile.display_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const normPositions = useMemo(
    () => positions.map((r, i) => normalizePosition(r, i)).filter((p) => p.netQty !== 0).slice(0, 5),
    [positions],
  );
  const normHoldings = useMemo(() => holdings.map((r, i) => normalizeHolding(r, i)).slice(0, 5), [holdings]);
  const recentOrders = useMemo(() => orders.map(localToUnified), [orders]);

  const portfolioValue = normHoldings.reduce((s, h) => s + (h.currentValue ?? 0), 0);
  const dayPnl = normPositions.reduce((s, p) => s + p.unrealizedPnl, 0) +
    normHoldings.reduce((s, h) => s + (h.dayPnl ?? 0), 0);

  const available = funds
    ? Number(funds.availableBalance ?? funds.availabelBalance ?? funds.sodLimit ?? 0)
    : null;
  const usedMargin = funds ? Number(funds.utilizedAmount ?? funds.usedMargin ?? 0) : null;

  return (
    <AppShell>
      <PageHeader
        title="Dashboard"
        subtitle={`Welcome ${displayName || summary?.user || ""} · GnKAlgo terminal`}
        action={
          <button type="button" onClick={load} className="rounded border border-[var(--line)] px-2.5 py-1 text-[11px]">
            Refresh
          </button>
        }
      />
      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4 mb-3">
        <SummaryTile label="Available Funds" value={available != null ? fmtINR(available) : "—"} />
        <SummaryTile label="Used Margin" value={usedMargin != null ? fmtINR(usedMargin) : "—"} />
        <SummaryTile label="Today's P&L" value={fmtINR(dayPnl)} pnl={dayPnl} />
        <SummaryTile label="Portfolio Value" value={fmtINR(portfolioValue)} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Open Positions" action={<Link href="/positions" className="text-[10px] text-[var(--accent)]">View all</Link>}>
          {normPositions.length ? (
            <PositionsTable positions={normPositions} onExit={() => {}} />
          ) : (
            <p className="p-3 text-xs text-[var(--muted)]">No open positions</p>
          )}
        </Panel>
        <Panel title="Recent Orders" action={<Link href="/orders" className="text-[10px] text-[var(--accent)]">View all</Link>}>
          {recentOrders.length ? (
            <OrdersTable orders={recentOrders} onView={() => {}} onRepeat={() => {}} />
          ) : (
            <p className="p-3 text-xs text-[var(--muted)]">No orders yet</p>
          )}
        </Panel>
        <Panel title="AI Signals" action={<Link href="/signals" className="text-[10px] text-[var(--accent)]">View all</Link>}>
          {signals.length ? <AISignalTable items={signals} /> : (
            <p className="p-3 text-xs text-[var(--muted)]">Generate signals from AI Signals</p>
          )}
        </Panel>
        <Panel title="Holdings" action={<Link href="/holdings" className="text-[10px] text-[var(--accent)]">View all</Link>}>
          {normHoldings.length ? (
            <HoldingsTable items={normHoldings} />
          ) : (
            <p className="p-3 text-xs text-[var(--muted)]">No holdings yet</p>
          )}
        </Panel>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-4 text-center">
        {[
          ["Orders", summary?.orders_count, "/orders"],
          ["Strategies", summary?.active_strategies, "/strategies"],
          ["Signals", summary?.signals_count, "/signals"],
          ["Dhan", summary?.broker_status?.dhan ?? "—", "/broker"],
        ].map(([label, value, href]) => (
          <Link
            key={label as string}
            href={href as string}
            className="rounded border border-[var(--line)] bg-[var(--panel-2)] px-2 py-2 hover:bg-[var(--panel)]"
          >
            <p className="text-[10px] uppercase text-[var(--muted)]">{label as string}</p>
            <p className="text-sm font-semibold text-white">{String(value ?? "—")}</p>
          </Link>
        ))}
      </div>
    </AppShell>
  );
}
