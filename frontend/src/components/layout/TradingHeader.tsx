"use client";

import { Logo } from "@/components/Logo";
import { LiveMarketTicker } from "@/components/market/LiveMarketTicker";
import { UserMenu } from "@/components/layout/UserMenu";

export function TradingHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-[var(--line)] bg-[var(--background)]">
      <div className="flex h-11 items-center justify-between gap-3 px-3 lg:px-4">
        <Logo href="/dashboard" size={32} variant="full" />
        <div className="flex items-center gap-2">
          <span className="hidden md:inline text-[10px] text-[var(--muted)]">www.gnkalgo.com</span>
          <UserMenu />
        </div>
      </div>
      <LiveMarketTicker />
    </header>
  );
}
