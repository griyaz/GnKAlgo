import { describe, expect, it } from "vitest";

import { resolveBackAction } from "@/components/ui/BackButton";
import { nextNavDepth } from "@/lib/navHistory";

describe("resolveBackAction", () => {
  it("goes back when there is an earlier in-app history entry", () => {
    expect(resolveBackAction(1, "/dashboard")).toEqual({ type: "back" });
    expect(resolveBackAction(5, "/dashboard")).toEqual({ type: "back" });
  });

  it("uses the fallback at the entry page (depth 0)", () => {
    expect(resolveBackAction(0, "/dashboard")).toEqual({
      type: "push",
      href: "/dashboard",
    });
  });

  it("uses the provided fallback route for nested pages", () => {
    expect(resolveBackAction(0, "/settings")).toEqual({
      type: "push",
      href: "/settings",
    });
  });

  it("falls back safely when depth is unknown", () => {
    expect(resolveBackAction(null, "/dashboard")).toEqual({
      type: "push",
      href: "/dashboard",
    });
  });
});

describe("nextNavDepth", () => {
  it("increments on forward navigation", () => {
    expect(nextNavDepth(0, false)).toBe(1);
    expect(nextNavDepth(3, false)).toBe(4);
  });

  it("decrements on back/forward popstate but never below zero", () => {
    expect(nextNavDepth(2, true)).toBe(1);
    expect(nextNavDepth(1, true)).toBe(0);
    expect(nextNavDepth(0, true)).toBe(0);
  });

  it("treats unknown current depth as zero", () => {
    expect(nextNavDepth(null, false)).toBe(1);
    expect(nextNavDepth(null, true)).toBe(0);
  });

  it("supports the return-to-entry-then-back loop safely", () => {
    // /settings (entry, depth 0) -> /settings/appearance (push -> 1)
    const afterPush = nextNavDepth(0, false);
    expect(afterPush).toBe(1);
    // Back on appearance triggers popstate -> depth 0 again at /settings
    const afterBack = nextNavDepth(afterPush, true);
    expect(afterBack).toBe(0);
    // Back on /settings now falls back instead of stepping outside the app
    expect(resolveBackAction(afterBack, "/dashboard")).toEqual({
      type: "push",
      href: "/dashboard",
    });
  });
});
