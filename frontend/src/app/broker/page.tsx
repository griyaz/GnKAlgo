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
  const [fyers, setFyers] = useState<BrokerStatus | null>(null);
  const [fyersLoading, setFyersLoading] = useState(false);

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

  const refreshFyers = useCallback(async () => {
    try {
      setFyers(await api<BrokerStatus>("/api/v1/brokers/fyers/status", {}, true));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load FYERS status");
    }
  }, []);

  const connectFyers = async () => {
    setFyersLoading(true);
    setError("");
    try {
      const result = await api<{ authorization_url: string }>("/api/v1/brokers/fyers/login", {}, true);
      window.location.assign(result.authorization_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to start FYERS connection");
      setFyersLoading(false);
    }
  };

  const disconnectFyers = async () => {
    if (!window.confirm("Disconnect FYERS from GnKAlgo?")) return;
    setFyersLoading(true);
    try {
      await api("/api/v1/brokers/fyers/connection", { method: "DELETE" }, true);
      await refreshFyers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to disconnect FYERS");
    } finally {
      setFyersLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    refreshFyers();
  }, [refresh, refreshFyers]);

  return (
    <AppShell>
      <PageHeader title="Broker" subtitle="Dhan connection for GnKAlgo trading" back />
      {error && <ErrorBanner message={error} />}

      <div className="grid gap-3 lg:grid-cols-2">
        <BrokerStatusCard status={status} onRefresh={refresh} loading={loading} />
        <Panel className="p-4">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-sm font-semibold text-white">FYERS</h2>
              <p className="mt-1 text-xs text-[var(--muted)]">API v3 OAuth connection</p>
            </div>
            <span className={`text-xs font-semibold uppercase ${fyers?.status === "connected" ? "text-[var(--profit)]" : "text-[var(--muted)]"}`}>
              {fyers?.status ?? "disconnected"}
            </span>
          </div>
          <dl className="mt-4 space-y-2 text-xs">
            <div className="flex justify-between"><dt className="text-[var(--muted)]">Client ID</dt><dd className="text-white">{fyers?.client_id ?? "—"}</dd></div>
            <div className="flex justify-between"><dt className="text-[var(--muted)]">Health</dt><dd className="text-white">{fyers?.health_status ?? "—"}</dd></div>
          </dl>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={connectFyers} disabled={fyersLoading} className="rounded bg-[var(--accent)] px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-50">
              {fyersLoading ? "Connecting…" : fyers?.status === "connected" ? "Reconnect FYERS" : "Connect FYERS"}
            </button>
            {fyers?.status === "connected" && <button type="button" onClick={disconnectFyers} disabled={fyersLoading} className="rounded border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-50">Disconnect</button>}
            <button type="button" onClick={refreshFyers} disabled={fyersLoading} className="rounded border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-50">Refresh</button>
          </div>
          <p className="mt-3 text-[10px] text-[var(--muted)]">Access tokens remain encrypted on the backend and are never displayed.</p>
        </Panel>
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
