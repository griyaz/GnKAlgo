"use client";

import { AppShell } from "@/components/AppShell";
import { SettingsNav } from "@/components/settings/SettingsNav";
import { ConnectedDevices } from "@/components/security/ConnectedDevices";
import { PageHeader, Panel } from "@/components/ui/terminal";

export default function ConnectedDevicesPage() {
  return (
    <AppShell>
      <PageHeader title="Connected Devices" subtitle="Manage active GnKAlgo sessions" back backHref="/settings" />
      <SettingsNav />
      <Panel className="p-4">
        <ConnectedDevices />
      </Panel>
    </AppShell>
  );
}
