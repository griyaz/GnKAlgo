/**
 * Session-scoped tracking of how deep the user is within GnKAlgo's own history
 * stack. The Back button uses this to decide between `router.back()` (there is a
 * real internal page behind us) and navigating to a fallback route (we are at
 * the entry point, a fresh tab, or arrived from an external site).
 *
 * The App Router does not expose a reliable history index, so we maintain our
 * own depth: forward navigations increment it, back/forward popstate events
 * decrement it. Kept in a small pure helper so it can be unit-tested.
 */
export const NAV_DEPTH_KEY = "gnk_nav_depth";

/**
 * Compute the next in-app navigation depth.
 *
 * @param current depth before this transition (defaults to 0 when unknown)
 * @param wasPop  whether this transition came from a popstate (back/forward)
 */
export function nextNavDepth(current: number | null, wasPop: boolean): number {
  const base = typeof current === "number" && Number.isFinite(current) ? current : 0;
  if (wasPop) {
    return Math.max(0, base - 1);
  }
  return base + 1;
}
