export function resolveApiBase(): string {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      // Talk to the API on the same loopback host the UI is served from so the
      // request Origin stays consistent (localhost UI -> localhost API,
      // 127.0.0.1 UI -> 127.0.0.1 API) and passes the backend CORS check.
      return process.env.NEXT_PUBLIC_API_URL || `http://${host}:8000`;
    }
    return "";
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

export function clearTokens() { /* The server clears authentication cookies. */ }

function cookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const item = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return item ? decodeURIComponent(item.slice(name.length + 1)) : null;
}

async function refreshAccessToken(): Promise<boolean> {
  const res = await fetch(`${resolveApiBase()}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": cookie("gnk_csrf") || "" },
    body: JSON.stringify({}),
  });
  if (!res.ok) return false;
  return true;
}

export async function api<T>(path: string, options: RequestInit = {}, auth = false): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (auth && options.method && !["GET", "HEAD"].includes(options.method.toUpperCase())) headers.set("X-CSRF-Token", cookie("gnk_csrf") || "");
  let res = await fetch(`${resolveApiBase()}${path}`, { ...options, headers, credentials: "include" });
  if (auth && res.status === 401) {
    const ok = await refreshAccessToken();
    if (ok) {
      const retryHeaders = new Headers(options.headers);
      retryHeaders.set("Content-Type", "application/json");
      if (options.method && !["GET", "HEAD"].includes(options.method.toUpperCase())) retryHeaders.set("X-CSRF-Token", cookie("gnk_csrf") || "");
      res = await fetch(`${resolveApiBase()}${path}`, { ...options, headers: retryHeaders, credentials: "include" });
    } else {
      clearTokens();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
      throw new Error("Session expired. Please login again.");
    }
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data as T;
}
