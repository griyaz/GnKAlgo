"use client";

import { PaymentInstructions } from "@/components/billing/PaymentInstructions";
import { BackButton } from "@/components/ui/BackButton";
import { CopyButton } from "@/components/billing/CopyButton";
import { api } from "@/lib/api";
import { Logo } from "@/components/Logo";
import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

type PaymentInstruction = {
  amount_inr: number;
  vpa: string;
  payee: string;
  reference: string;
  send_line: string;
  reference_line: string;
};

type Checkout = {
  payment_id: string;
  reference: string;
  amount_inr: number;
  days: number;
  plan_code: string;
  plan_label?: string;
  is_renewal?: boolean;
  pay_url?: string;
  intents: { upi: string; gpay: string; phonepe: string; paytm: string; vpa: string; payee: string };
  payment_instruction?: PaymentInstruction;
  instructions?: string;
  support_email?: string;
  admin_url?: string;
};

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1 sm:grid-cols-[140px_1fr] sm:gap-4 sm:items-start py-1">
      <dt className="text-slate-400 text-sm shrink-0">{label}</dt>
      <dd className="min-w-0 overflow-visible text-sm">{children}</dd>
    </div>
  );
}

function PayInner() {
  const params = useSearchParams();
  const [checkout, setCheckout] = useState<Checkout | null>(null);
  const [utr, setUtr] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const paymentId = params.get("id");
    const raw = sessionStorage.getItem("gnk_checkout");
    if (raw) {
      const parsed = JSON.parse(raw) as Checkout;
      if (!paymentId || parsed.payment_id === paymentId) {
        setCheckout(parsed);
        setLoading(false);
        return;
      }
    }
    if (!paymentId) {
      setLoading(false);
      return;
    }
    api<Checkout>(`/api/v1/billing/payments/${paymentId}`, {}, true)
      .then((data) => {
        setCheckout(data);
        sessionStorage.setItem("gnk_checkout", JSON.stringify(data));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load payment"))
      .finally(() => setLoading(false));
  }, [params]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!checkout) return;
    setError("");
    try {
      const res = await api<{ message: string }>(
        `/api/v1/billing/payments/${checkout.payment_id}/utr`,
        { method: "POST", body: JSON.stringify({ utr }) },
        true,
      );
      setMessage(res.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit UTR");
    }
  }

  if (loading) {
    return <main className="mx-auto max-w-lg px-6 py-12 text-slate-400">Loading payment…</main>;
  }

  if (!checkout) {
    return (
      <main className="mx-auto max-w-lg px-6 py-12">
        <Logo href="/subscribe" size={44} />
        <p className="mt-6 text-slate-400">No payment in progress. Choose a plan first.</p>
        <a href="/subscribe" className="mt-4 inline-block text-[#2ee6a6]">Back to plans</a>
      </main>
    );
  }

  const vpa = checkout.payment_instruction?.vpa ?? checkout.intents.vpa;
  const payee = checkout.payment_instruction?.payee ?? checkout.intents.payee;
  const reference = checkout.payment_instruction?.reference ?? checkout.reference;
  const amount = checkout.payment_instruction?.amount_inr ?? checkout.amount_inr;

  const qr = `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(checkout.intents.upi)}`;
  const apps = [
    { href: checkout.intents.phonepe, label: "Open PhonePe" },
    { href: checkout.intents.gpay, label: "Open GPay" },
    { href: checkout.intents.paytm, label: "Open Paytm" },
    { href: checkout.intents.upi, label: "Any UPI app" },
  ];
  const support = checkout.support_email || "support@gnkalgo.com";

  return (
    <main className="mx-auto max-w-2xl px-4 sm:px-6 py-12 overflow-visible">
      <Logo href="/subscribe" size={44} />
      <div className="mt-4">
        <BackButton fallbackHref="/subscribe" />
      </div>
      <h1 className="mt-6 text-2xl font-semibold">
        {checkout.is_renewal ? "Renew subscription" : "Complete UPI payment"}
      </h1>
      <p className="mt-2 text-slate-400">UPI only · PhonePe · Google Pay · Paytm</p>

      <PaymentInstructions
        className="mt-6"
        amount_inr={amount}
        vpa={vpa}
        payee={payee}
        reference={reference}
      />

      <section className="mt-6 rounded-2xl border border-[#1d3542] bg-[#0d1b24]/70 p-5 overflow-visible">
        <h2 className="text-sm font-medium text-[#2ee6a6]">Order details</h2>
        <dl className="mt-3 space-y-2">
          <DetailRow label="Plan">
            <span className="font-medium">{checkout.plan_label || checkout.plan_code}</span>
          </DetailRow>
          <DetailRow label="Duration">
            <span>{checkout.days} day{checkout.days > 1 ? "s" : ""}</span>
          </DetailRow>
          <DetailRow label="Amount (pay exactly)">
            <span className="text-lg font-semibold text-[#2ee6a6]">₹{checkout.amount_inr}</span>
          </DetailRow>
          <DetailRow label="UPI ID (VPA)">
            <span className="inline-flex flex-wrap items-center gap-2 overflow-visible">
              <span className="font-mono font-semibold whitespace-nowrap shrink-0 overflow-visible text-[#2ee6a6]">
                {vpa}
              </span>
              <CopyButton text={vpa} label="Copy UPI ID" />
            </span>
          </DetailRow>
          <DetailRow label="Payee name">
            <span>{payee}</span>
          </DetailRow>
          <DetailRow label="Payment reference">
            <span className="inline-flex flex-wrap items-center gap-2 overflow-visible">
              <span className="font-mono text-xs font-semibold whitespace-nowrap shrink-0 overflow-visible">
                {reference}
              </span>
              <CopyButton text={reference} label="Copy reference" />
            </span>
          </DetailRow>
          <DetailRow label="Payment ID">
            <span className="font-mono text-xs text-slate-500 break-all">{checkout.payment_id}</span>
          </DetailRow>
        </dl>
      </section>

      <section className="mt-6 rounded-2xl border border-[#1d3542] p-5 overflow-visible">
        <h2 className="font-medium">How to pay</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-slate-300">
          <li>Scan the QR code or tap your UPI app below.</li>
          <li>
            Pay <strong>exactly ₹{checkout.amount_inr}</strong> — not less or more.
          </li>
          <li className="break-words">
            UPI ID:{" "}
            <strong className="font-mono font-semibold whitespace-nowrap shrink-0">{vpa}</strong>
            {" · "}
            Name: <strong>{payee}</strong>
          </li>
          <li>After payment, open PhonePe / GPay / Paytm → Transaction history → copy <strong>UTR</strong> or <strong>UPI Ref No.</strong></li>
          <li>Paste UTR below and tap <strong>I have paid</strong>.</li>
          <li>We confirm manually (usually within a few hours). You get access when status is confirmed.</li>
        </ol>
        {checkout.instructions && (
          <p className="mt-3 text-xs text-slate-500 break-words">{checkout.instructions}</p>
        )}
      </section>

      <div className="mt-6 flex flex-col items-center">
        <img src={qr} alt="UPI QR code" className="rounded-xl bg-white p-3" width={240} height={240} />
        <p className="mt-2 text-xs text-slate-500">Scan with any UPI app</p>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-2">
        {apps.map((app) => (
          <a
            key={app.label}
            href={app.href}
            className="rounded-xl border border-[#1d3542] px-3 py-3 text-center text-sm font-medium hover:bg-[#123348]"
          >
            {app.label}
          </a>
        ))}
      </div>

      <form onSubmit={onSubmit} className="mt-8 rounded-2xl border border-[#1d3542] bg-[#0d1b24]/70 p-5">
        <h2 className="font-medium">Submit payment proof</h2>
        <label className="mt-4 block text-sm">UTR / UPI Reference Number</label>
        <input
          className="mt-1 w-full rounded-lg border border-[#1d3542] bg-[#071018] px-3 py-2"
          value={utr}
          onChange={(e) => setUtr(e.target.value)}
          placeholder="12-digit UTR from your UPI app"
          minLength={6}
          required
        />
        {error && <p className="mt-3 text-sm text-[#ff6b6b]">{error}</p>}
        {message && (
          <p className="mt-3 text-sm text-[#2ee6a6]">
            {message} Track status on <a href="/dashboard" className="underline">Dashboard</a>.
          </p>
        )}
        <button className="mt-4 w-full rounded-xl bg-[#2ee6a6] py-2.5 font-semibold text-[#071018]">
          I have paid — submit UTR
        </button>
      </form>

      <section className="mt-6 rounded-2xl border border-[#1d3542] p-5 text-sm text-slate-400">
        <h2 className="font-medium text-slate-200">Help & support</h2>
        <ul className="mt-2 space-y-1">
          <li>Email: <a href={`mailto:${support}`} className="text-[#3aa0ff]">{support}</a></li>
          <li>Wrong amount sent? Email us with UTR and registered email.</li>
          <li>Cards and net banking are not accepted — UPI only.</li>
          <li>
            <a href="/subscribe" className="text-[#2ee6a6]">Change plan</a>
            {" · "}
            <a href="/login" className="text-[#2ee6a6]">Login</a>
          </li>
        </ul>
      </section>
    </main>
  );
}

export default function PayPage() {
  return (
    <Suspense fallback={<main className="p-10 text-slate-400">Loading…</main>}>
      <PayInner />
    </Suspense>
  );
}
