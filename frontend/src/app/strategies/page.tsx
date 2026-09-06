"use client";

import { AppShell } from "@/components/AppShell";
import { BackButton } from "@/components/ui/BackButton";
import { api } from "@/lib/api";
import { FormEvent, useEffect, useState } from "react";

type Strategy = {
  id: string;
  name: string;
  description: string | null;
  symbol: string;
  rules_json: string;
  status: string;
  paper_mode: boolean;
  max_quantity: number;
  schedule_enabled: boolean;
  interval_minutes: number;
  last_scheduled_run_at: string | null;
};

type StrategyType = "simple" | "smc_intraday";
type EntryMode = "order_block" | "fvg" | "bos";
type SideMode = "BUY" | "SELL" | "AUTO";

type FormState = {
  name: string;
  description: string;
  symbol: string;
  strategy_type: StrategyType;
  action: SideMode;
  qty: number;
  timeframe: "5m" | "15m";
  entry_mode: EntryMode;
  stop_loss_buffer_pct: number;
  target_rr: number;
  paper_mode: boolean;
  max_quantity: number;
  schedule_enabled: boolean;
  interval_minutes: number;
};

const DEFAULT_FORM: FormState = {
  name: "SMC intraday paper",
  description: "",
  symbol: "RELIANCE",
  strategy_type: "smc_intraday",
  action: "AUTO",
  qty: 1,
  timeframe: "15m",
  entry_mode: "fvg",
  stop_loss_buffer_pct: 0.1,
  target_rr: 2,
  paper_mode: true,
  max_quantity: 100,
  schedule_enabled: false,
  interval_minutes: 15,
};

type ParsedRules = {
  type: StrategyType;
  action: string;
  qty: number;
  timeframe?: string;
  entry?: string;
  target_rr?: number;
  stop_loss_buffer_pct?: number;
};

function parseRules(json: string): ParsedRules {
    try {
      const raw = JSON.parse(json || "{}");
      const type: StrategyType = raw.type === "smc_intraday" ? "smc_intraday" : "simple";
      const qty = Number(raw.qty) > 0 ? Number(raw.qty) : 1;
      if (type === "smc_intraday") {
        return {
          type,
          action: raw.action || "AUTO",
          qty,
          timeframe: raw.timeframe || "15m",
          entry: raw.entry || "fvg",
          target_rr: raw.target_rr ?? 2,
          stop_loss_buffer_pct: raw.stop_loss_buffer_pct ?? 0.1,
        };
      }
    const action = raw.action === "SELL" ? "SELL" : "BUY";
    return { type, action, qty };
  } catch {
    return { type: "simple", action: "BUY", qty: 1 };
  }
}

function formPayload(form: FormState, editingId: string | null) {
  const base = {
    name: form.name,
    description: form.description || null,
    symbol: form.symbol,
    strategy_type: form.strategy_type,
    action: form.action,
    qty: form.qty,
    paper_mode: form.paper_mode,
    max_quantity: form.max_quantity,
    schedule_enabled: form.schedule_enabled,
    interval_minutes: form.schedule_enabled ? form.interval_minutes : 0,
  };
  if (form.strategy_type === "smc_intraday") {
    Object.assign(base, {
      timeframe: form.timeframe,
      entry_mode: form.entry_mode,
      stop_loss_buffer_pct: form.stop_loss_buffer_pct,
      target_rr: form.target_rr,
    });
  }
  return editingId ? base : { ...base, description: form.description || undefined };
}

function rulesPreview(form: FormState): object {
  if (form.strategy_type === "smc_intraday") {
    return {
      type: "smc_intraday",
      timeframe: form.timeframe,
      entry: form.entry_mode,
      action: form.action,
      qty: form.qty,
      stop_loss_buffer_pct: form.stop_loss_buffer_pct,
      target_rr: form.target_rr,
    };
  }
  return { type: "simple", action: form.action, qty: form.qty };
}

export default function StrategiesPage() {
  const [items, setItems] = useState<Strategy[]>([]);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setItems(await api<Strategy[]>("/api/v1/strategies/", {}, true));
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  function startEdit(s: Strategy) {
    const rules = parseRules(s.rules_json);
    setEditingId(s.id);
    setForm({
      name: s.name,
      description: s.description || "",
      symbol: s.symbol,
      strategy_type: rules.type,
      action: (rules.action as SideMode) || "BUY",
      qty: rules.qty,
      timeframe: (rules.timeframe as "5m" | "15m") || "15m",
      entry_mode: (rules.entry as EntryMode) || "fvg",
      stop_loss_buffer_pct: rules.stop_loss_buffer_pct ?? 0.1,
      target_rr: rules.target_rr ?? 2,
      paper_mode: s.paper_mode,
      max_quantity: s.max_quantity,
      schedule_enabled: s.schedule_enabled,
      interval_minutes: s.interval_minutes > 0 ? s.interval_minutes : 15,
    });
    setMessage("");
    setError("");
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(DEFAULT_FORM);
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");
    const payload = formPayload(form, editingId);
    try {
      if (editingId) {
        await api(`/api/v1/strategies/${editingId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        }, true);
        setMessage("Strategy updated.");
      } else {
        await api("/api/v1/strategies/", {
          method: "POST",
          body: JSON.stringify(payload),
        }, true);
        setMessage("Strategy created.");
        setForm(DEFAULT_FORM);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function run(id: string) {
    setError("");
    try {
      const res = await api<{ notes: string; status: string }>(
        `/api/v1/strategies/${id}/run`,
        { method: "POST" },
        true,
      );
      setMessage(`${res.status}: ${res.notes}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    }
  }

  async function togglePause(s: Strategy) {
    setError("");
    const paused = s.status === "PAUSED";
    try {
      await api(`/api/v1/strategies/${s.id}`, {
        method: "PUT",
        body: JSON.stringify({ status: paused ? (s.paper_mode ? "PAPER" : "LIVE") : "PAUSED" }),
      }, true);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Status update failed");
    }
  }

  return (
    <AppShell>
      <BackButton className="mb-2" />
      <h1 className="text-3xl font-semibold">Strategy builder</h1>
      <p className="mt-2 text-sm text-slate-400">
        Simple BUY/SELL or SMC intraday (entry, stop loss, target on chart rules). Paper first.
      </p>
      {error && <p className="mt-3 text-[#ff6b6b]">{error}</p>}
      {message && <p className="mt-3 text-sm text-[#2ee6a6]">{message}</p>}

      <form onSubmit={save} className="mt-6 rounded-2xl border border-[#1d3542] bg-[#0d1b24]/70 p-5">
        <h2 className="font-medium">{editingId ? "Edit strategy" : "New strategy"}</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <label className="block text-sm">
            Name
            <input
              className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </label>
          <label className="block text-sm">
            Symbol (NSE)
            <input
              className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
              value={form.symbol}
              onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
              required
            />
          </label>
          <label className="block text-sm md:col-span-2">
            Description
            <input
              className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </label>
          <label className="block text-sm">
            Strategy type
            <select
              className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
              value={form.strategy_type}
              onChange={(e) =>
                setForm({
                  ...form,
                  strategy_type: e.target.value as StrategyType,
                  action: e.target.value === "smc_intraday" ? "AUTO" : "BUY",
                })
              }
            >
              <option value="simple">Simple (fixed side)</option>
              <option value="smc_intraday">SMC intraday (entry / SL / target)</option>
            </select>
          </label>
          <label className="block text-sm">
            Side
            <select
              className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
              value={form.action}
              onChange={(e) => setForm({ ...form, action: e.target.value as SideMode })}
            >
              {form.strategy_type === "smc_intraday" ? (
                <>
                  <option value="AUTO">AUTO (from setup)</option>
                  <option value="BUY">BUY only</option>
                  <option value="SELL">SELL only</option>
                </>
              ) : (
                <>
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </>
              )}
            </select>
          </label>
          {form.strategy_type === "smc_intraday" && (
            <>
              <label className="block text-sm">
                Timeframe
                <select
                  className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
                  value={form.timeframe}
                  onChange={(e) => setForm({ ...form, timeframe: e.target.value as "5m" | "15m" })}
                >
                  <option value="5m">5 minute</option>
                  <option value="15m">15 minute</option>
                </select>
              </label>
              <label className="block text-sm">
                Entry (SMC)
                <select
                  className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
                  value={form.entry_mode}
                  onChange={(e) => setForm({ ...form, entry_mode: e.target.value as EntryMode })}
                >
                  <option value="fvg">Fair value gap (FVG)</option>
                  <option value="order_block">Order block</option>
                  <option value="bos">Break of structure (BOS)</option>
                </select>
              </label>
              <label className="block text-sm">
                SL buffer (%)
                <input
                  type="number"
                  min={0}
                  max={5}
                  step={0.05}
                  className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
                  value={form.stop_loss_buffer_pct}
                  onChange={(e) => setForm({ ...form, stop_loss_buffer_pct: Number(e.target.value) })}
                />
              </label>
              <label className="block text-sm">
                Target (R:R)
                <input
                  type="number"
                  min={0.5}
                  max={10}
                  step={0.5}
                  className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
                  value={form.target_rr}
                  onChange={(e) => setForm({ ...form, target_rr: Number(e.target.value) })}
                />
              </label>
            </>
          )}
          <label className="block text-sm">
            Quantity
            <input
              type="number"
              min={1}
              className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
              value={form.qty}
              onChange={(e) => setForm({ ...form, qty: Number(e.target.value) })}
              required
            />
          </label>
          <label className="block text-sm">
            Max qty cap
            <input
              type="number"
              min={1}
              className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
              value={form.max_quantity}
              onChange={(e) => setForm({ ...form, max_quantity: Number(e.target.value) })}
            />
          </label>
          <label className="flex items-center gap-3 text-sm pt-6">
            <input
              type="checkbox"
              checked={form.paper_mode}
              onChange={(e) => setForm({ ...form, paper_mode: e.target.checked })}
            />
            Paper mode (no real money)
          </label>
          <label className="flex items-center gap-3 text-sm pt-6">
            <input
              type="checkbox"
              checked={form.schedule_enabled}
              onChange={(e) => setForm({ ...form, schedule_enabled: e.target.checked })}
            />
            Run on schedule
          </label>
          {form.schedule_enabled && (
            <label className="block text-sm">
              Every N minutes
              <input
                type="number"
                min={1}
                max={1440}
                className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
                value={form.interval_minutes}
                onChange={(e) => setForm({ ...form, interval_minutes: Number(e.target.value) })}
                required
              />
            </label>
          )}
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          <button type="submit" className="rounded-xl bg-[#2ee6a6] px-5 py-2 font-semibold text-[#071018]">
            {editingId ? "Save changes" : "Create strategy"}
          </button>
          {editingId && (
            <button type="button" onClick={cancelEdit} className="rounded-xl border border-[#1d3542] px-5 py-2 text-sm">
              Cancel
            </button>
          )}
        </div>
        <p className="mt-3 text-xs text-slate-500">
          rules_json: {JSON.stringify(rulesPreview(form))}
        </p>
      </form>

      <div className="mt-8 grid gap-4">
        {items.map((s) => {
          const rules = parseRules(s.rules_json);
          const label =
            rules.type === "smc_intraday"
              ? `SMC ${rules.entry} ${rules.timeframe} · ${rules.action} × ${rules.qty} · R:R ${rules.target_rr}`
              : `${rules.action} × ${rules.qty}`;
          return (
            <div key={s.id} className="rounded-2xl border border-[#1d3542] p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{s.name}</p>
                  <p className="mt-1 text-sm text-slate-400">
                    {s.symbol} · {label} · {s.paper_mode ? "paper" : "live"} · {s.status}
                  </p>
                  {s.schedule_enabled && (
                    <p className="mt-1 text-sm text-[#2ee6a6]">
                      Scheduled every {s.interval_minutes} min
                      {s.last_scheduled_run_at ? ` · last run ${s.last_scheduled_run_at}` : ""}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => startEdit(s)} className="rounded-lg border border-[#1d3542] px-3 py-2 text-sm">
                    Edit
                  </button>
                  <button onClick={() => run(s.id)} className="rounded-lg border border-[#1d3542] px-3 py-2 text-sm">
                    Run once
                  </button>
                  {s.schedule_enabled && (
                    <button onClick={() => togglePause(s)} className="rounded-lg border border-[#1d3542] px-3 py-2 text-sm">
                      {s.status === "PAUSED" ? "Resume schedule" : "Pause schedule"}
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        {!items.length && <p className="text-slate-500">No strategies yet. Create one above.</p>}
      </div>
    </AppShell>
  );
}
