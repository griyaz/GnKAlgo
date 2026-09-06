"use client";

import { AppShell } from "@/components/AppShell";
import { BackButton } from "@/components/ui/BackButton";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

type Stats = {
  registered: number;
  verified: number;
  logged_in_7d: number;
  never_logged_in: number;
  inactive: number;
  active_subscribers: number;
  payments_awaiting_utr_review: number;
  share_url: string;
};

type UserRow = {
  id: string;
  email: string;
  full_name: string | null;
  is_verified: boolean;
  last_login_at: string | null;
  created_at: string;
  activity: "active" | "inactive" | "never_logged_in";
};

type PaymentRow = {
  id: string;
  user_id: string;
  plan_code: string;
  amount_inr: number;
  reference: string;
  status: string;
  utr: string | null;
  created_at: string;
};

export default function AdminPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [payments, setPayments] = useState<PaymentRow[]>([]);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [meEmail, setMeEmail] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [killSwitch, setKillSwitch] = useState<{ active: boolean; reason: string | null } | null>(null);

  async function load() {
    setError("");
    try {
      const me = await api<{ email: string; is_admin?: boolean }>("/api/v1/auth/me", {}, true);
      setMeEmail(me.email);
      setIsAdmin(Boolean(me.is_admin));
      if (!me.is_admin) {
        setError("Admin only — your account is not an admin yet.");
        return;
      }
      const [s, u, p, k] = await Promise.all([
        api<Stats>("/api/v1/admin/stats", {}, true),
        api<UserRow[]>("/api/v1/admin/users", {}, true),
        api<PaymentRow[]>("/api/v1/admin/payments", {}, true),
        api<{ active: boolean; reason: string | null }>("/api/v1/admin/trading/kill-switch", {}, true),
      ]);
      setStats(s);
      setUsers(u);
      setPayments(p);
      setKillSwitch(k);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Admin access denied");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function confirm(id: string) {
    setNote("");
    try {
      const res = await api<{ message: string }>(`/api/v1/admin/payments/${id}/confirm`, { method: "POST" }, true);
      setNote(res.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirm failed");
    }
  }

  async function toggleKillSwitch() {
    if (!killSwitch) return;
    const active = !killSwitch.active;
    if (!active && !window.confirm("Disable the emergency stop and permit eligible LIVE orders?")) return;
    const updated = await api<{ active: boolean; reason: string | null }>("/api/v1/admin/trading/kill-switch", {
      method: "PUT",
      body: JSON.stringify({ active, reason: active ? "Activated by administrator" : "Explicitly disabled by administrator" }),
    }, true);
    setKillSwitch(updated);
  }

  return (
    <AppShell>
      <BackButton className="mb-2" />
      <h1 className="text-3xl font-semibold">Admin</h1>
      <p className="mt-1 text-slate-400">Registered users, logins, and UPI payments</p>
      {meEmail && (
        <p className="mt-2 text-sm text-slate-500">
          Logged in as <span className="text-slate-300">{meEmail}</span>
          {isAdmin ? " · admin" : " · not admin"}
        </p>
      )}
      {error && (
        <div className="mt-4 rounded-2xl border border-[#ff6b6b]/40 bg-[#1a0d0d]/50 p-5 text-sm">
          <p className="text-[#ff6b6b] font-medium">{error}</p>
          {!isAdmin && (
            <div className="mt-3 text-slate-300 space-y-2">
              <p className="font-medium text-slate-200">How to get admin access (on Oracle server):</p>
              <ol className="list-decimal pl-5 space-y-1">
                <li>Edit <code className="text-xs bg-[#071018] px-1">/opt/gnkalgo/.env</code></li>
                <li>Set <code className="text-xs bg-[#071018] px-1">ADMIN_EMAILS={meEmail || "your-email@gnkalgo.com"}</code></li>
                <li>Restart backend: <code className="text-xs bg-[#071018] px-1">docker compose -f docker-compose.prod.yml up -d --force-recreate backend</code></li>
                <li>Sign out and <strong>login again</strong> with that email</li>
                <li>Reopen <a href="/admin" className="text-[#2ee6a6]">/admin</a></li>
              </ol>
              <p className="text-xs text-slate-500 mt-2">
                Or in Postgres: <code>UPDATE users SET is_admin = true WHERE email = &apos;{meEmail}&apos;;</code>
              </p>
            </div>
          )}
        </div>
      )}
      {note && <p className="mt-3 text-[#2ee6a6]">{note}</p>}

      {killSwitch && <section className="mt-6 rounded-2xl border border-[#ff6b6b]/50 p-5"><h2 className="font-semibold">Emergency kill switch: {killSwitch.active ? "ACTIVE" : "DISABLED"}</h2><p className="mt-1 text-sm text-slate-400">{killSwitch.reason}</p><button type="button" onClick={toggleKillSwitch} className="mt-3 rounded-lg border border-[#ff6b6b] px-3 py-2 text-sm">{killSwitch.active ? "Disable with confirmation" : "Activate emergency stop"}</button></section>}

      {stats && (
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Registered", stats.registered],
            ["Email verified", stats.verified],
            ["Active (login 7 days)", stats.logged_in_7d],
            ["Inactive", stats.inactive],
            ["Never logged in", stats.never_logged_in],
            ["Paid subscribers", stats.active_subscribers],
            ["UTR to review", stats.payments_awaiting_utr_review],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-2xl border border-[#1d3542] bg-[#0d1b24]/70 p-5">
              <p className="text-sm text-slate-400">{label}</p>
              <p className="mt-2 text-2xl font-semibold">{value}</p>
            </div>
          ))}
        </div>
      )}

      <p className="mt-6 text-sm text-slate-400">
        Share with users: <span className="text-[#2ee6a6]">{stats?.share_url}</span>
      </p>

      <h2 className="mt-10 text-xl font-medium">UPI payments</h2>
      <div className="mt-3 overflow-x-auto rounded-2xl border border-[#1d3542]">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-[#0d1b24] text-slate-400">
            <tr>
              <th className="px-3 py-2">Plan</th>
              <th className="px-3 py-2">₹</th>
              <th className="px-3 py-2">Ref</th>
              <th className="px-3 py-2">UTR</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id} className="border-t border-[#1d3542]">
                <td className="px-3 py-2">{p.plan_code}</td>
                <td className="px-3 py-2">{p.amount_inr}</td>
                <td className="px-3 py-2 font-mono text-xs">{p.reference}</td>
                <td className="px-3 py-2 font-mono text-xs">{p.utr || "—"}</td>
                <td className="px-3 py-2">{p.status}</td>
                <td className="px-3 py-2">
                  {p.status !== "confirmed" && (
                    <button onClick={() => confirm(p.id)} className="rounded-lg bg-[#2ee6a6] px-2 py-1 text-xs font-semibold text-[#071018]">
                      Confirm
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!payments.length && (
              <tr>
                <td className="px-3 py-4 text-slate-500" colSpan={6}>No payments yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <h2 className="mt-10 text-xl font-medium">Users</h2>
      <div className="mt-3 overflow-x-auto rounded-2xl border border-[#1d3542]">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-[#0d1b24] text-slate-400">
            <tr>
              <th className="px-3 py-2">Email</th>
              <th className="px-3 py-2">Verified</th>
              <th className="px-3 py-2">Activity</th>
              <th className="px-3 py-2">Last login</th>
              <th className="px-3 py-2">Registered</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-[#1d3542]">
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2">{u.is_verified ? "yes" : "no"}</td>
                <td className="px-3 py-2">{u.activity}</td>
                <td className="px-3 py-2 text-xs text-slate-400">{u.last_login_at || "—"}</td>
                <td className="px-3 py-2 text-xs text-slate-400">{u.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
