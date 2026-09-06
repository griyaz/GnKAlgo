"use client";

import { useRouter } from "next/navigation";

import { NAV_DEPTH_KEY } from "@/lib/navHistory";

export type BackButtonProps = {
  /** Visible label. Defaults to "Back". */
  label?: string;
  /** Route to use when there is no safe in-app page to return to. Defaults to "/dashboard". */
  fallbackHref?: string;
  /** Extra classes merged onto the button. */
  className?: string;
  /** Disable the control. */
  disabled?: boolean;
};

type BackAction = { type: "back" } | { type: "push"; href: string };

/**
 * Decide how the Back button should navigate given the current in-app history
 * depth (see {@link NavigationTracker}). A depth greater than zero means the
 * user reached this page by navigating within GnKAlgo, so `router.back()`
 * returns to a real internal page. Otherwise (direct link, new tab, or arrival
 * from an external site) we route to the fallback instead of stepping outside
 * the app.
 *
 * Kept pure so the decision can be unit-tested without a DOM.
 */
export function resolveBackAction(
  navDepth: number | null,
  fallbackHref: string,
): BackAction {
  if (typeof navDepth === "number" && navDepth > 0) {
    return { type: "back" };
  }
  return { type: "push", href: fallbackHref };
}

function readNavDepth(): number | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(NAV_DEPTH_KEY);
    if (raw === null) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

export function BackButton({
  label = "Back",
  fallbackHref = "/dashboard",
  className = "",
  disabled = false,
}: BackButtonProps) {
  const router = useRouter();

  function handleBack() {
    if (disabled) return;
    const action = resolveBackAction(readNavDepth(), fallbackHref);
    if (action.type === "back") {
      router.back();
    } else {
      router.push(action.href);
    }
  }

  return (
    <button
      type="button"
      onClick={handleBack}
      disabled={disabled}
      aria-label={label}
      className={`inline-flex items-center gap-1.5 rounded border border-[var(--line)] bg-[var(--panel)] px-2.5 py-1 text-xs font-medium text-[var(--muted)] transition-colors hover:bg-[var(--panel-2)] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
        className="shrink-0"
      >
        <path d="M19 12H5" />
        <path d="M12 19l-7-7 7-7" />
      </svg>
      {label}
    </button>
  );
}
