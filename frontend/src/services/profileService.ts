import { api, resolveApiBase } from "@/lib/api";

export type Profile = {
  id: string;
  email: string;
  full_name: string | null;
  display_name: string | null;
  phone: string | null;
  gender: string | null;
  date_of_birth: string | null;
  profile_photo_url: string | null;
  theme_preference: string;
  is_verified: boolean;
  mfa_enabled: boolean;
  client_id: string;
  email_verified: boolean;
  phone_verified: boolean;
  created_at: string;
  trading_segments: {
    code: string;
    name: string;
    status: string;
    icon: string;
  }[];
};

export async function fetchProfile(): Promise<Profile> {
  return api<Profile>("/api/v1/profile/", {}, true);
}

export async function updateProfile(data: Record<string, unknown>): Promise<Profile> {
  return api<Profile>("/api/v1/profile/", {
    method: "PATCH",
    body: JSON.stringify(data),
  }, true);
}

export async function uploadProfilePhoto(file: File): Promise<Profile> {
  const form = new FormData();
  form.append("file", file);
  const base = resolveApiBase();
  const res = await fetch(`${base}/api/v1/profile/photo`, {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": document.cookie.split("; ").find((p) => p.startsWith("gnk_csrf="))?.split("=")[1] || "" },
    body: form,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Upload failed");
  return data as Profile;
}

export async function removeProfilePhoto(): Promise<Profile> {
  return api<Profile>("/api/v1/profile/photo", { method: "DELETE" }, true);
}
