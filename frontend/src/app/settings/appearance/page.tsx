"use client";

import { AppShell } from "@/components/AppShell";
import { SettingsNav } from "@/components/settings/SettingsNav";
import { ThemeSelector } from "@/components/settings/ThemeSelector";
import { PageHeader } from "@/components/ui/terminal";

export default function AppearanceSettingsPage() {
  return (
    <AppShell>
      <PageHeader title="Appearance" subtitle="Choose your GnKAlgo terminal theme" back backHref="/settings" />
      <SettingsNav />
      <ThemeSelector />
    </AppShell>
  );
}
