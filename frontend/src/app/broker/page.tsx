"use client";

import { AppShell } from "@/components/AppShell";
import { BrokerStatusCard } from "@/components/broker/BrokerStatusCard";
import { ErrorBanner, PageHeader, Panel } from "@/components/ui/terminal";
import { api } from "@/lib/api";
import { useCallback, useEffect, useState } from "react";

type BrokerStatus = {
  broker: string;
  status: string;
  client_id?: string | null;
  health_status?: string;
  last_health_check?: string | null;
  error?: string | null;
};

export default function BrokerPage() {
  const [status, setStatus] = useState<BrokerStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api<BrokerStatus>("/api/v1/portfolio/broker-status?broker=dhan", {}, true);
      setStatus(res);
      if (res.error) setError(res.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load broker status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <AppShell>
      <PageHeader title="Broker" subtitle="Dhan connection for GnKAlgo trading" back />
      {error && <ErrorBanner message={error} />}

      <div className="grid gap-3 lg:grid-cols-2">
        <BrokerStatusCard status={status} onRefresh={refresh} loading={loading} />
        <Panel className="p-4">
          <h3 className="text-xs font-semibold uppercase text-[var(--muted)]">After connection</h3>
          <ul className="mt-3 space-y-2 text-xs text-[var(--muted)]">
            <li>Funds sync on Money page</li>
            <li>Positions on Positions page</li>
            <li>Holdings on Holdings page</li>
            <li>Broker orders on Orders page</li>
          </ul>
          <p className="mt-4 text-[10px] text-[var(--muted)]">
            Live Dhan order APIs require MFA and a whitelisted static IP. Paper trading works without broker calls.
          </p>
        </Panel>
      </div>
    </AppShell>
  );
}
