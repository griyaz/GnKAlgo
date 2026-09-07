"use client";

import { fmtNum, fmtPct } from "@/lib/format";
import type { Quote } from "@/services/chartDataService";

type CrosshairInfo = {
  o?: number;
  h?: number;
  l?: number;
  c?: number;
  vol?: number | null;
  changePct?: number;
} | null;

export function ChartHeader({
  quote,
  displayName,
  marketLabel,
  marketOpen,
  wsStatus,
  crosshair,
  dataSource,
}: {
  quote: Quote | null;
  displayName: string;
  marketLabel: string;
  marketOpen: boolean;
  wsStatus: string;
  crosshair: CrosshairInfo;
  dataSource?: string;
}) {
  const ltp = crosshair?.c ?? quote?.ltp;
  const change = quote?.change ?? 0;
  const changePct = crosshair?.changePct ?? quote?.change_pct ?? 0;
  const up = change > 0;
  const down = change < 0;
  const color = up ? "text-[var(--profit)]" : down ? "text-[var(--loss)]" : "text-[var(--muted)]";
  const sign = change > 0 ? "+" : "";

  const wsLabel =
    wsStatus === "CONNECTED"
      ? "Live"
      : wsStatus === "CONNECTING" || wsStatus === "RECONNECTING"
        ? "Reconnecting…"
        : wsStatus === "ERROR"
          ? "Offline"
          : "Offline";

  const wsColor =
    wsStatus === "CONNECTED"
      ? "text-[var(--profit)]"
      : wsStatus === "CONNECTING" || wsStatus === "RECONNECTING"
        ? "text-[var(--accent-2)]"
        : "text-[var(--muted)]";

  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--line)] px-3 py-2">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold text-white">{quote?.symbol ?? displayName}</h2>
          <span className="text-[11px] text-[var(--muted)]">{displayName}</span>
          <span className="rounded bg-[var(--panel-2)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">
            {quote?.exchange ?? "NSE"}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-baseline gap-3">
          <span className="text-xl font-semibold tabular-nums text-white">{ltp == null ? "—" : fmtNum(ltp)}</span>
          <span className={`text-sm tabular-nums ${color}`}>
            {sign}{fmtNum(change)} ({fmtPct(changePct)})
          </span>
        </div>
        {crosshair && (
          <p className="mt-1 text-[10px] tabular-nums text-[var(--muted)]">
            O {fmtNum(crosshair.o)} · H {fmtNum(crosshair.h)} · L {fmtNum(crosshair.l)} · C{" "}
            {fmtNum(crosshair.c)}
            {crosshair.changePct != null && ` · ${fmtPct(crosshair.changePct)}`}
            {crosshair.vol != null && ` · Vol ${fmtNum(crosshair.vol, 0)}`}
          </p>
        )}
      </div>
      <div className="flex flex-col items-end gap-1 text-[11px]">
        <span className={marketOpen ? "text-[var(--profit)]" : "text-[var(--muted)]"}>
          <span className="mr-1">●</span>
          {marketLabel}
        </span>
        <span className={wsColor}>
          <span className="mr-1">●</span>
          {wsLabel}
        </span>
        {dataSource === "mock_dev" && (
          <span className="text-[10px] text-[var(--warning)]">Dev mock data</span>
        )}
      </div>
    </div>
  );
}
