"use client";

import { AppShell } from "@/components/AppShell";
import { FundsSummaryCard, MarginBreakdown } from "@/components/funds/FundsSummary";
import {
  EmptyState,
  ErrorBanner,
  PageHeader,
  Panel,
} from "@/components/ui/terminal";
import { api } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { useCallback, useEffect, useState } from "react";

export default function MoneyPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [connected, setConnected] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api<{
        connected: boolean;
        data: Record<string, unknown> | null;
        updated_at?: string | null;
        error?: string;
      }>("/api/v1/portfolio/funds?broker=dhan", {}, true);
      setConnected(res.connected);
      setData(res.data);
      setUpdatedAt(res.updated_at ?? new Date().toISOString());
      if (res.error) setError(res.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load funds");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <AppShell>
      <PageHeader
        back
        title="Money"
        subtitle="Funds and margin from your broker"
        action={
          <div className="flex items-center gap-2 text-[11px] text-[var(--muted)]">
            {updatedAt && <span>Updated {fmtTime(updatedAt)}</span>}
            <button
              type="button"
              disabled={loading}
              onClick={load}
              className="rounded border border-[var(--line)] px-2.5 py-1 disabled:opacity-50"
            >
              Refresh
            </button>
          </div>
        }
      />
      {error && <ErrorBanner message={error} />}

      {!connected ? (
        <EmptyState title="Broker not connected" detail="Connect Dhan to view funds and margin." />
      ) : (
        <div className="space-y-3">
          <FundsSummaryCard data={data} />
          <MarginBreakdown data={data} />
          <Panel className="p-3">
            <h3 className="text-xs font-semibold uppercase text-[var(--muted)]">Actions</h3>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                disabled
                className="rounded border border-[var(--line)] px-3 py-1.5 text-xs text-[var(--muted)] opacity-60"
                title="Coming soon"
              >
                Add Funds — Coming Soon
              </button>
              <button
                type="button"
                disabled
                className="rounded border border-[var(--line)] px-3 py-1.5 text-xs text-[var(--muted)] opacity-60"
                title="Coming soon"
              >
                Withdraw — Coming Soon
              </button>
            </div>
            <p className="mt-2 text-[10px] text-[var(--muted)]">
              Bank payments are not enabled in GnKAlgo yet. Values shown are from your broker API.
            </p>
          </Panel>
        </div>
      )}
    </AppShell>
  );
}
