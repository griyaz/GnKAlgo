"use client";

import { useMarketTicker } from "@/hooks/useMarketTicker";
import {
  formatChange,
  formatNumber,
  type ChangeDirection,
} from "@/hooks/useMarketTicker";
import type { MarketStatusCode, TickerItem } from "@/services/market/tickerTypes";

function statusStyle(status: MarketStatusCode): { label: string; color: string } {
  switch (status) {
    case "OPEN":
      return { label: "Market Open", color: "text-[var(--profit)]" };
    case "PRE_OPEN":
      return { label: "Pre-Open", color: "text-[var(--accent-2)]" };
    case "HOLIDAY":
      return { label: "Market Holiday", color: "text-[var(--muted)]" };
    case "CLOSED":
      return { label: "Market Closed", color: "text-[var(--muted)]" };
    default:
      return { label: "Market", color: "text-[var(--muted)]" };
  }
}

function directionColor(direction: ChangeDirection): string {
  if (direction === "up") return "text-[var(--profit)]";
  if (direction === "down") return "text-[var(--loss)]";
  return "text-[var(--muted)]";
}

function IndexChip({ item }: { item: TickerItem }) {
  const { direction, arrow, text } = formatChange(item.change, item.change_percent);
  const color = directionColor(direction);
  const label = `${item.display_name} ${formatNumber(item.ltp)}, ${
    direction === "up" ? "up" : direction === "down" ? "down" : "unchanged"
  } ${text}`;
  return (
    <div
      className={`flex shrink-0 items-center gap-2 border-r border-[var(--line)] px-3 py-1.5 last:border-r-0 ${
        item.is_stale ? "opacity-50" : ""
      }`}
      aria-label={label}
      title={label}
    >
      <span className="text-[11px] font-medium text-[var(--muted)] whitespace-nowrap">
        {item.display_name}
      </span>
      <span className="text-xs font-semibold text-[var(--foreground)] tabular-nums">
        {formatNumber(item.ltp)}
      </span>
      <span className={`text-[11px] tabular-nums whitespace-nowrap ${color}`}>
        {arrow ? `${arrow} ` : ""}
        {text}
      </span>
    </div>
  );
}

export function LiveMarketTicker() {
  const { indexes, marketStatus, provider, connected, stale, demo } =
    useMarketTicker();

  const status = statusStyle(marketStatus);
  const loop = indexes.length ? [...indexes, ...indexes] : [];

  // Feed indicator never shows a stale value as if it were live.
  const feed = stale
    ? { label: "Data delayed", color: "text-[var(--loss)]" }
    : connected
      ? { label: "Live", color: "text-[var(--profit)]" }
      : { label: "Feed disconnected", color: "text-[var(--muted)]" };

  return (
    <div
      className="w-full border-b border-[var(--line)] bg-[var(--panel)]"
      role="marquee"
      aria-label="Live market index ticker"
    >
      <div className="flex h-[var(--ticker-height)] items-center gap-2 px-2">
        <div
          className={`flex shrink-0 items-center gap-1.5 px-2 text-[11px] font-medium ${status.color}`}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
          {status.label}
        </div>

        {demo && (
          <span className="shrink-0 rounded bg-[var(--accent-2)]/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--accent-2)]">
            Demo Data
          </span>
        )}

        <div className="ticker-wrap relative flex-1 min-w-0">
          {loop.length ? (
            <div className="ticker-track flex w-max">
              {loop.map((item, i) => (
                <IndexChip key={`${item.symbol}-${i}`} item={item} />
              ))}
            </div>
          ) : (
            <div className="px-3 text-[11px] text-[var(--muted)]">
              Connecting to market feed…
            </div>
          )}
        </div>

        <div className="hidden shrink-0 items-center gap-2 px-2 sm:flex">
          <span className={`flex items-center gap-1 text-[10px] font-medium ${feed.color}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
            {feed.label}
          </span>
          {provider && provider !== "NONE" && (
            <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">
              {provider}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default LiveMarketTicker;
