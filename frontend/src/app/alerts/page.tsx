"use client";

import Link from "next/link";

import { AppShell } from "@/components/AppShell";
import { EmptyState, PageHeader, Panel } from "@/components/ui/terminal";

export default function AlertsPage() {
  return (
    <AppShell>
      <PageHeader title="Alerts" subtitle="Price and webhook alerts" back />
      <Panel className="p-4">
        <EmptyState
          title="Alerts"
          detail="Use Webhooks for inbound trading signals and outbound notifications."
        />
        <Link
          href="/webhooks"
          className="mt-4 inline-block text-xs text-[var(--accent)]"
        >
          Open Webhooks →
        </Link>
      </Panel>
    </AppShell>
  );
}
