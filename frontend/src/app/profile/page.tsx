"use client";

import { AppShell } from "@/components/AppShell";
import { ProfileDetails } from "@/components/profile/ProfileDetails";
import { ProfileHeader } from "@/components/profile/ProfileHeader";
import { TradingSegments } from "@/components/profile/TradingSegments";
import { ErrorBanner, PageHeader } from "@/components/ui/terminal";
import {
  fetchProfile,
  removeProfilePhoto,
  updateProfile,
  uploadProfilePhoto,
  type Profile,
} from "@/services/profileService";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

export default function ProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setProfile(await fetchProfile());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load profile");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!profile && !error) {
    return (
      <AppShell>
        <p className="text-[var(--text-secondary)]">Loading profile…</p>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageHeader title="Profile" subtitle="Account identity and trading segments" back />
      {error && <ErrorBanner message={error} />}
      {profile && (
        <div className="space-y-3">
          <ProfileHeader
            profile={profile}
            onUpload={async (file) => {
              const p = await uploadProfilePhoto(file);
              setProfile(p);
            }}
            onRemove={async () => {
              const p = await removeProfilePhoto();
              setProfile(p);
            }}
          />
          <ProfileDetails
            profile={profile}
            onSave={async (data) => {
              const p = await updateProfile(data);
              setProfile(p);
            }}
          />
          <TradingSegments segments={profile.trading_segments} />
          <section className="rounded border border-[var(--border)] bg-[var(--surface)] p-4">
            <h3 className="text-xs font-semibold uppercase text-[var(--text-secondary)] mb-2">Security</h3>
            <Link href="/settings/security/devices" className="text-sm text-[var(--accent)]">
              Connected Devices →
            </Link>
          </section>
        </div>
      )}
    </AppShell>
  );
}
