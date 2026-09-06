"use client";

import { AppShell } from "@/components/AppShell";
import { AISignalTable } from "@/components/ai/AISignalTable";
import { ErrorBanner, PageHeader, Panel } from "@/components/ui/terminal";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

type Signal = {
  id: string;
  symbol: string;
  action: string;
  confidence: number;
  price?: number | null;
  created_at: string;
};

export default function SignalsPage() {
  const [items, setItems] = useState<Signal[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    setItems(await api<Signal[]>("/api/v1/signals/", {}, true));
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function generate() {
    setLoading(true);
    setError("");
    try {
      await api("/api/v1/signals/generate", { method: "POST" }, true);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generate failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell>
      <PageHeader
        back
        title="AI Signals"
        subtitle="GnKAlgo ML signals — never auto-executed without an approved strategy"
        action={
          <button
            type="button"
            onClick={generate}
            disabled={loading}
            className="rounded bg-[var(--accent)] px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
          >
            {loading ? "Generating…" : "Generate"}
          </button>
        }
      />
      {error && <ErrorBanner message={error} />}
      <Panel>
        {items.length ? (
          <AISignalTable items={items} />
        ) : (
          <p className="p-4 text-xs text-[var(--muted)]">No signals yet. Click Generate to run the model.</p>
        )}
      </Panel>
      <p className="mt-3 text-[10px] text-[var(--muted)]">
        Not investment advice. Signals use RSI, MACD, and volume features. STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL mapping applies to model output.
      </p>
    </AppShell>
  );
}
