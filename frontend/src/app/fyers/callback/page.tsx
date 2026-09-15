"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";

export default function FyersCallbackPage() {
  const [message, setMessage] = useState("Connecting FYERS…");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authCode = params.get("auth_code") || params.get("code");
    const state = params.get("state");
    window.history.replaceState({}, document.title, "/fyers/callback");
    if (!authCode || !state) {
      setMessage("FYERS authorization was incomplete. Please try again.");
      setFailed(true);
      return;
    }
    api("/api/v1/brokers/fyers/callback", {
      method: "POST",
      body: JSON.stringify({ auth_code: authCode, state }),
    }, true).then(() => {
      setMessage("FYERS connected successfully. Redirecting…");
      window.setTimeout(() => { window.location.href = "/broker"; }, 700);
    }).catch((error: unknown) => {
      setMessage(error instanceof Error ? error.message : "FYERS connection failed. Please try again.");
      setFailed(true);
    });
  }, []);

  return (
    <AppShell>
      <div className="mx-auto max-w-lg rounded border border-[var(--line)] bg-[var(--panel)] p-6">
        <h1 className="text-lg font-semibold text-white">FYERS connection</h1>
        <p className={`mt-3 text-sm ${failed ? "text-[var(--loss)]" : "text-[var(--muted)]"}`}>{message}</p>
      </div>
    </AppShell>
  );
}
