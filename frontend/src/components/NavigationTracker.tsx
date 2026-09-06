"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { NAV_DEPTH_KEY, nextNavDepth } from "@/lib/navHistory";

/**
 * Invisible tracker that keeps a session-scoped count of how deep the user is
 * within GnKAlgo's own navigation stack. Mounted once at the app root so it runs
 * on every route. The {@link BackButton} reads this value to choose between
 * `router.back()` and a fallback route.
 *
 * - Fresh document load with no existing depth → seed at 0 (entry page).
 * - Client-side forward navigation (push) → increment.
 * - Back/forward via popstate (browser buttons or `router.back()`) → decrement.
 *
 * A depth that survives a page refresh is intentionally preserved: the browser
 * keeps its real back stack across reloads, so Back should still work.
 */
export function NavigationTracker() {
  const pathname = usePathname();
  const lastPathname = useRef<string | null>(null);
  const wasPop = useRef(false);

  useEffect(() => {
    const onPopState = () => {
      wasPop.current = true;
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    let current: number | null = null;
    try {
      const raw = window.sessionStorage.getItem(NAV_DEPTH_KEY);
      current = raw === null ? null : Number(raw);
    } catch {
      current = null;
    }

    // First render of this document.
    if (lastPathname.current === null) {
      lastPathname.current = pathname;
      if (current === null) {
        try {
          window.sessionStorage.setItem(NAV_DEPTH_KEY, "0");
        } catch {
          // Ignore storage failures (private mode, etc.).
        }
      }
      return;
    }

    // Ignore effect runs that are not real path transitions.
    if (pathname === lastPathname.current) return;
    lastPathname.current = pathname;

    const pop = wasPop.current;
    wasPop.current = false;
    try {
      window.sessionStorage.setItem(NAV_DEPTH_KEY, String(nextNavDepth(current, pop)));
    } catch {
      // Ignore storage failures.
    }
  }, [pathname]);

  return null;
}
