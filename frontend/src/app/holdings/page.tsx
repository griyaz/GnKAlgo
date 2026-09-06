"use client";

import { AppShell } from "@/components/AppShell";
import { HoldingsTable } from "@/components/holdings/HoldingsTable";
import {
  EmptyState,
  ErrorBanner,
  PageHeader,
  Panel,
  SummaryTile,
} from "@/components/ui/terminal";
import { api } from "@/lib/api";
import { fmtINR } from "@/lib/format";
import { normalizeHolding } from "@/lib/holdings";
import { useCallback, useEffect, useMemo, useState } from "react";

export default function HoldingsPage() {
  const [raw, setRaw] = useState<Record<string, unknown>[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await api<{
        connected: boolean;
        items: Record<string, unknown>[];
        error?: string;
      }>("/api/v1/portfolio/holdings?broker=dhan", {}, true);
      setConnected(res.connected);
      setRaw(res.items || []);
      if (res.error) setError(res.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load holdings");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const items = useMemo(() => raw.map((r, i) => normalizeHolding(r, i)), [raw]);

  const summary = useMemo(() => {
    const current = items.reduce((s, h) => s + (h.currentValue ?? 0), 0);
    const invested = items.reduce((s, h) => s + (h.investmentValue ?? 0), 0);
    const totalPnl = items.reduce((s, h) => s + (h.totalPnl ?? 0), 0);
    const dayPnl = items.reduce((s, h) => s + (h.dayPnl ?? 0), 0);
    return { current, invested, totalPnl, dayPnl };
  }, [items]);

  return (
    <AppShell>
      <PageHeader
        back
        title="Holdings"
        subtitle="Delivery portfolio from connected broker"
        action={
          <button type="button" onClick={load} className="rounded border border-[var(--line)] px-2.5 py-1 text-[11px]">
            Refresh
          </button>
        }
      />
      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4 mb-3">
        <SummaryTile label="Current Value" value={fmtINR(summary.current)} />
        <SummaryTile label="Investment" value={fmtINR(summary.invested)} />
        <SummaryTile label="Total Returns" value={fmtINR(summary.totalPnl)} pnl={summary.totalPnl} />
        <SummaryTile label="Today's P&L" value={fmtINR(summary.dayPnl)} pnl={summary.dayPnl} />
      </div>

      <Panel>
        {!connected ? (
          <EmptyState title="Broker not connected" detail="Connect Dhan to sync holdings." />
        ) : items.length ? (
          <HoldingsTable items={items} />
        ) : (
          <EmptyState title="No holdings" detail="Your delivery holdings will appear here." />
        )}
      </Panel>
    </AppShell>
  );
}
