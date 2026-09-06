"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: "◫" },
  { href: "/charts", label: "Charts", icon: "⌁" },
  { href: "/orders", label: "Orders", icon: "⇄" },
  { href: "/positions", label: "Positions", icon: "▣" },
  { href: "/holdings", label: "Holdings", icon: "▤" },
  { href: "/money", label: "Money", icon: "₹" },
  { href: "/strategies", label: "Strategies", icon: "⚙" },
  { href: "/signals", label: "AI Signals", icon: "✦" },
  { href: "/alerts", label: "Alerts", icon: "!" },
  { href: "/broker", label: "Broker", icon: "⇌" },
  { href: "/profile", label: "Profile", icon: "○" },
  { href: "/settings", label: "Settings", icon: "⚙" },
  { href: "/subscribe", label: "Subscribe", icon: "★" },
];

export function TradingSidebar({ isAdmin }: { isAdmin?: boolean }) {
  const pathname = usePathname();
  const items = [...NAV, ...(isAdmin ? [{ href: "/admin", label: "Admin", icon: "⚡" }] : [])];

  return (
    <aside className="hidden lg:flex w-[200px] shrink-0 flex-col border-r border-[var(--line)] bg-[var(--panel)]">
      <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {items.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2 rounded px-2.5 py-2 text-xs font-medium transition-colors ${
                active
                  ? "bg-[var(--panel-2)] text-[var(--accent)] border border-[var(--line)]"
                  : "text-[var(--muted)] hover:bg-[var(--panel-2)] hover:text-white border border-transparent"
              }`}
            >
              <span className="w-4 text-center opacity-70">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
