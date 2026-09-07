"use client";

import { AppShell } from "@/components/AppShell";
import { BackButton } from "@/components/ui/BackButton";
import { ErrorBanner, Panel } from "@/components/ui/terminal";
import { api } from "@/lib/api";
import { FormEvent, useEffect, useState } from "react";

type Alert = {
  id: string;
  symbol: string;
  exchange: string;
  operator: string;
  threshold: number;
  status: "ACTIVE" | "TRIGGERED" | "PAUSED";
  recurring: boolean;
  created_at: string;
  triggered_at: string | null;
};

export default function AlertsPage() {
  const [items, setItems] = useState<Alert[]>([]);
  const [symbol, setSymbol] = useState("NIFTY50");
  const [operator, setOperator] = useState(">");
  const [threshold, setThreshold] = useState("");
  const [recurring, setRecurring] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setItems(await api<Alert[]>("/api/v1/alerts/", {}, true));
  }

  useEffect(() => {
    load().catch((err) => setError(err instanceof Error ? err.message : "Failed to load alerts"));
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      await api("/api/v1/alerts/", {
        method: "POST",
        body: JSON.stringify({
          symbol,
          exchange: "NSE",
          operator,
          threshold: Number(threshold),
          recurring,
        }),
      }, true);
      setThreshold("");
      setMessage("Alert created.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create alert");
    }
  }

  async function toggle(item: Alert) {
    try {
      await api(`/api/v1/alerts/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: item.status === "ACTIVE" ? "PAUSED" : "ACTIVE" }),
      }, true);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update alert");
    }
  }

  return (
    <AppShell>
      <BackButton className="mb-2" />
      <h1 className="text-2xl font-semibold">Alerts</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Server-evaluated price alerts. Your browser does not need to remain open.
      </p>
      {error && <ErrorBanner message={error} />}
      {message && <p className="mt-3 text-sm text-[var(--profit)]">{message}</p>}
      <Panel className="mt-4 p-4">
        <form onSubmit={create} className="grid gap-3 md:grid-cols-5">
          <label className="text-xs">
            Symbol
            <input className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--panel-2)] px-2 py-2" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} required />
          </label>
          <label className="text-xs">
            Condition
            <select className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--panel-2)] px-2 py-2" value={operator} onChange={(e) => setOperator(e.target.value)}>
              <option value=">">Price above</option>
              <option value=">=">Price at or above</option>
              <option value="<">Price below</option>
              <option value="<=">Price at or below</option>
            </select>
          </label>
          <label className="text-xs">
            Threshold
            <input className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--panel-2)] px-2 py-2" type="number" min="0.01" step="0.01" value={threshold} onChange={(e) => setThreshold(e.target.value)} required />
          </label>
          <label className="flex items-center gap-2 pt-5 text-xs">
            <input type="checkbox" checked={recurring} onChange={(e) => setRecurring(e.target.checked)} />
            Recurring
          </label>
          <button className="mt-5 rounded bg-[var(--accent)] px-3 py-2 text-xs font-semibold text-black" type="submit">Create alert</button>
        </form>
      </Panel>
      <Panel className="mt-4 divide-y divide-[var(--line)]">
        {items.length === 0 && <p className="p-4 text-sm text-[var(--text-secondary)]">No alerts yet.</p>}
        {items.map((item) => (
          <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
            <div>
              <p className="font-medium">{item.symbol} · Price {item.operator} {item.threshold}</p>
              <p className="text-xs text-[var(--text-secondary)]">{item.recurring ? "Recurring" : "Trigger once"} · {item.triggered_at ? `Triggered ${new Date(item.triggered_at).toLocaleString("en-IN")}` : "Not triggered"}</p>
            </div>
            <button type="button" onClick={() => toggle(item)} className="rounded border border-[var(--line)] px-3 py-1.5 text-xs">{item.status === "ACTIVE" ? "Pause" : "Resume"}</button>
          </div>
        ))}
      </Panel>
    </AppShell>
  );
}
