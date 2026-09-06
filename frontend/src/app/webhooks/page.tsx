"use client";

import { AppShell } from "@/components/AppShell";
import { BackButton } from "@/components/ui/BackButton";
import { api } from "@/lib/api";
import { FormEvent, useEffect, useState } from "react";

type Webhook = {
  id: string;
  name: string;
  direction: string;
  inbound_url?: string | null;
  secret?: string | null;
  token: string;
};

export default function WebhooksPage() {
  const [items, setItems] = useState<Webhook[]>([]);
  const [name, setName] = useState("TradingView inbound");
  const [createdSecret, setCreatedSecret] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setItems(await api<Webhook[]>("/api/v1/webhooks/", {}, true));
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    const created = await api<Webhook>("/api/v1/webhooks/", {
      method: "POST",
      body: JSON.stringify({ name, direction: "INBOUND" }),
    }, true);
    setCreatedSecret(created.secret || "");
    await load();
  }

  return (
    <AppShell>
      <BackButton className="mb-2" />
      <h1 className="text-3xl font-semibold">Webhooks</h1>
      <p className="mt-2 text-sm text-slate-400">
        POST JSON with symbol, action, and qty to the inbound URL. Required headers:
        X-Gnkalgo-Secret and X-Gnkalgo-Signature (hex HMAC-SHA256 of the raw body).
      </p>
      {error && <p className="mt-3 text-[#ff6b6b]">{error}</p>}
      <form onSubmit={create} className="mt-6 flex gap-3">
        <input className="rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="rounded-xl bg-[#2ee6a6] px-4 py-2 font-semibold text-[#071018]">Create inbound</button>
      </form>
      {createdSecret && <p className="mt-3 text-sm text-[#2ee6a6] break-all">Save this secret now: {createdSecret}</p>}
      <div className="mt-6 space-y-3">
        {items.map((w) => (
          <div key={w.id} className="rounded-2xl border border-[#1d3542] p-5 text-sm">
            <p className="font-medium">{w.name} · {w.direction}</p>
            <p className="mt-2 break-all text-slate-400">{w.inbound_url}</p>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
