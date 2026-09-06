"use client";

import { AppShell } from "@/components/AppShell";
import { BackButton } from "@/components/ui/BackButton";
import { SettingsNav } from "@/components/settings/SettingsNav";
import { api } from "@/lib/api";
import { FormEvent, useEffect, useState } from "react";

type Me = { email: string; full_name?: string | null; mfa_enabled: boolean; is_verified: boolean };
type Broker = { id: string; broker: string; health_status: string; is_active: boolean };
type BillingMe = {
  active: boolean;
  subscription: {
    plan_code: string;
    expires_at: string;
    active: boolean;
    auto_renew_enabled: boolean;
    auto_renew_plan_code: string | null;
  } | null;
  pending_renewal: { pay_url: string; amount_inr: number; plan_label: string } | null;
};
type Plan = { code: string; label: string };

export default function SettingsPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [billing, setBilling] = useState<BillingMe | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [renewPlan, setRenewPlan] = useState("5DAYS");
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [broker, setBroker] = useState("dhan");
  const [accessToken, setAccessToken] = useState("");
  const [clientId, setClientId] = useState("");
  const [qr, setQr] = useState("");
  const [secret, setSecret] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [mfaCode, setMfaCode] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    setMe(await api<Me>("/api/v1/auth/me", {}, true));
    setBrokers(await api<Broker[]>("/api/v1/brokers/connections", {}, true));
    const bill = await api<BillingMe>("/api/v1/billing/me", {}, true);
    setBilling(bill);
    const planRes = await api<{ plans: Plan[] }>("/api/v1/billing/plans");
    setPlans(planRes.plans);
    if (bill.subscription?.auto_renew_plan_code) {
      setRenewPlan(bill.subscription.auto_renew_plan_code);
    } else if (bill.subscription?.plan_code) {
      setRenewPlan(bill.subscription.plan_code);
    }
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function connect(e: FormEvent) {
    e.preventDefault();
    setError("");
    await api("/api/v1/brokers/connect", {
      method: "POST",
      body: JSON.stringify({ broker, access_token: accessToken, client_id: clientId || null }),
    }, true);
    setMessage(`${broker} credentials saved (encrypted). Paper-trade before going live.`);
    setAccessToken("");
    await load();
  }

  async function setupMfa() {
    const res = await api<{ qr_uri: string; secret: string; backup_codes: string[] }>("/api/v1/auth/mfa/setup", { method: "POST" }, true);
    setQr(res.qr_uri);
    setSecret(res.secret);
    setBackupCodes(res.backup_codes || []);
    setMessage("Add this secret in Google Authenticator or Authy, then enter a 6-digit code. Save backup codes now.");
  }

  async function enableMfa(e: FormEvent) {
    e.preventDefault();
    await api("/api/v1/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code: mfaCode }) }, true);
    setMessage("MFA enabled. Live orders now allowed after Dhan is connected.");
    await load();
  }

  async function toggleAutoRenew(enabled: boolean) {
    setError("");
    try {
      const res = await api<{ message: string }>("/api/v1/billing/auto-renew", {
        method: "PUT",
        body: JSON.stringify({ enabled, plan_code: enabled ? renewPlan : null }),
      }, true);
      setMessage(res.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update auto-renew");
    }
  }

  const brokerNeedsClientId = broker === "dhan" || broker === "fyers";

  return (
    <AppShell>
      <BackButton className="mb-2" />
      <h1 className="text-lg font-semibold text-[var(--text-primary)]">Settings</h1>
      <SettingsNav />
      <p className="mt-2 text-slate-400">{me?.email} · verified: {String(me?.is_verified)} · MFA: {String(me?.mfa_enabled)}</p>
      {error && <p className="mt-3 text-[#ff6b6b]">{error}</p>}
      {message && <p className="mt-3 text-sm text-[#2ee6a6] break-all">{message}</p>}

      <section id="subscription" className="mt-8 scroll-mt-8 rounded-2xl border border-[#1d3542] p-5">
        <h2 className="font-medium">Auto-renew (UPI)</h2>
        <p className="mt-2 text-sm text-slate-400">
          Before your plan expires, we email a UPI pay link. Pay and submit UTR — your plan extends from the current expiry date.
          (UPI Autopay mandate via Razorpay/PhonePe Business can be added later.)
        </p>
        {billing?.subscription ? (
          <div className="mt-4 text-sm text-slate-300">
            <p>Plan: {billing.subscription.plan_code} · expires {billing.subscription.expires_at}</p>
            <p className="mt-1">
              Auto-renew:{" "}
              <span className={billing.subscription.auto_renew_enabled ? "text-[#2ee6a6]" : "text-slate-500"}>
                {billing.subscription.auto_renew_enabled ? "ON" : "OFF"}
              </span>
            </p>
            {billing.pending_renewal && (
              <p className="mt-2 text-[#2ee6a6]">
                Renewal due: ₹{billing.pending_renewal.amount_inr} —{" "}
                <a href={billing.pending_renewal.pay_url}>Pay now</a>
              </p>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <select
                className="rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2 text-sm"
                value={renewPlan}
                onChange={(e) => setRenewPlan(e.target.value)}
                disabled={billing.subscription.auto_renew_enabled}
              >
                {plans.map((p) => (
                  <option key={p.code} value={p.code}>{p.label}</option>
                ))}
              </select>
              {billing.subscription.auto_renew_enabled ? (
                <button
                  type="button"
                  onClick={() => toggleAutoRenew(false)}
                  className="rounded-xl border border-[#1d3542] px-4 py-2 text-sm"
                >
                  Turn off auto-renew
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => toggleAutoRenew(true)}
                  className="rounded-xl bg-[#2ee6a6] px-4 py-2 text-sm font-semibold text-[#071018]"
                >
                  Enable auto-renew
                </button>
              )}
            </div>
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-500">
            <a href="/subscribe" className="text-[#2ee6a6]">Subscribe</a> first to enable auto-renew.
          </p>
        )}
      </section>

      <section id="mfa" className="mt-6 scroll-mt-8 rounded-2xl border border-[#1d3542] p-5">
        <h2 className="font-medium">1. Multi-factor authentication</h2>
        <p className="mt-2 text-sm text-slate-400">Required before live (real-money) orders. Paper orders work without MFA.</p>
        {me?.mfa_enabled ? (
          <p className="mt-4 text-[#2ee6a6]">MFA is on for this account.</p>
        ) : (
          <>
            <button type="button" onClick={setupMfa} className="mt-4 rounded-lg border border-[#1d3542] px-3 py-2 text-sm">Generate TOTP secret</button>
            {secret && <p className="mt-3 break-all text-xs text-slate-400">Secret: {secret}</p>}
            {backupCodes.length > 0 && (
              <p className="mt-2 break-all text-xs text-[#2ee6a6]">Backup codes: {backupCodes.join(" ")}</p>
            )}
            {qr && <p className="mt-2 break-all text-xs text-slate-500">{qr}</p>}
            <form onSubmit={enableMfa} className="mt-4 flex flex-wrap gap-3">
              <input className="rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2" placeholder="6-digit code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} />
              <button className="rounded-xl bg-[#2ee6a6] px-4 py-2 font-semibold text-[#071018]">Enable MFA</button>
            </form>
          </>
        )}
      </section>

      <section id="broker" className="mt-6 scroll-mt-8 rounded-2xl border border-[#1d3542] p-5">
        <h2 className="font-medium">2. Connect a broker (paper first)</h2>
        <p className="mt-2 text-sm text-slate-400">
          Choose your broker and paste its API credentials. Tokens are encrypted at rest and
          never exposed to the browser or in API responses.
        </p>
        <ul className="mt-2 list-disc pl-5 text-sm text-slate-400">
          <li><strong>Dhan</strong> — access token + client ID. Live orders need a <strong>static public IP</strong> whitelisted at Dhan (Oracle reserved IP).</li>
          <li><strong>Groww</strong> — access token. Needs an active Groww Trading API subscription.</li>
          <li><strong>FYERS</strong> — access token + client/app ID (e.g. <code>ABCD1234-100</code>). Token expires daily.</li>
          <li><strong>Upstox</strong> — access token (Upstox API v2).</li>
        </ul>
        <form onSubmit={connect} className="mt-4 grid gap-3 md:grid-cols-2">
          <select className="rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2" value={broker} onChange={(e) => setBroker(e.target.value)}>
            <option value="dhan">Dhan</option>
            <option value="groww">Groww (optional)</option>
            <option value="fyers">FYERS</option>
            <option value="upstox">Upstox</option>
          </select>
          {brokerNeedsClientId ? (
            <input className="rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2" placeholder={broker === "fyers" ? "Client / App ID (e.g. ABCD1234-100)" : "Client ID"} value={clientId} onChange={(e) => setClientId(e.target.value)} />
          ) : (
            <div className="hidden md:block" aria-hidden="true" />
          )}
          <input className="md:col-span-2 rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2" placeholder="Access token / API key" value={accessToken} onChange={(e) => setAccessToken(e.target.value)} type="password" />
          <button className="rounded-xl bg-[#2ee6a6] px-4 py-2 font-semibold text-[#071018]">Save encrypted</button>
        </form>
        <ul className="mt-4 text-sm text-slate-400">
          {brokers.map((b) => (
            <li key={b.id}>{b.broker} · {b.health_status}</li>
          ))}
        </ul>
      </section>
    </AppShell>
  );
}
