"use client";

import { fmtINR } from "@/lib/format";
import type { NormalizedPosition } from "@/lib/portfolio";

export function ExitPositionModal({
  position,
  onClose,
  onConfirm,
  loading,
}: {
  position: NormalizedPosition | null;
  onClose: () => void;
  onConfirm: () => void;
  loading?: boolean;
}) {
  if (!position) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="w-full max-w-sm rounded border border-[var(--line)] bg-[var(--panel)] p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold text-white">Exit Position</h3>
        <p className="mt-2 text-xs text-[var(--muted)]">{position.symbol}</p>
        <p className="mt-1 text-xs text-white">Net Qty: {position.netQty}</p>
        <p className="text-xs text-white">Market Price: {fmtINR(position.ltp)}</p>
        <p className="mt-3 text-[11px] text-[var(--muted)]">
          This sends a live Dhan market order to close the position. Confirm only if you intend to exit.
        </p>
        <div className="mt-4 flex gap-2">
          <button type="button" onClick={onClose} className="flex-1 rounded border border-[var(--line)] py-2 text-xs">
            Cancel
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={onConfirm}
            className="flex-1 rounded bg-[var(--loss)] py-2 text-xs font-semibold text-white disabled:opacity-50"
          >
            {loading ? "Submitting…" : "Exit at Market"}
          </button>
        </div>
      </div>
    </div>
  );
}
