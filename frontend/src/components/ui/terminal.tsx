import { fmtINR } from "@/lib/format";
import { BackButton } from "@/components/ui/BackButton";

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-[var(--panel-2)] ${className}`} />;
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="rounded border border-[var(--line)] bg-[var(--panel)] p-8 text-center">
      <p className="text-sm font-medium text-white">{title}</p>
      {detail && <p className="mt-1 text-xs text-[var(--muted)]">{detail}</p>}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded border border-[var(--loss)]/30 bg-[var(--loss)]/10 px-3 py-2 text-xs text-[var(--loss)]">
      {message}
    </div>
  );
}

export function PnlText({
  value,
  className = "",
  prefix = "",
}: {
  value: number | null | undefined;
  className?: string;
  prefix?: string;
}) {
  const n = value ?? 0;
  const color = n > 0 ? "text-[var(--profit)]" : n < 0 ? "text-[var(--loss)]" : "text-[var(--muted)]";
  return (
    <span className={`tabular-nums ${color} ${className}`}>
      {prefix}{fmtINR(n)}
    </span>
  );
}

export function Panel({
  children,
  className = "",
  title,
  action,
}: {
  children: React.ReactNode;
  className?: string;
  title?: string;
  action?: React.ReactNode;
}) {
  return (
    <section className={`rounded border border-[var(--line)] bg-[var(--panel)] ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({
  title,
  subtitle,
  action,
  back,
  backHref,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  /** Show a Back button above the title on secondary/nested pages. */
  back?: boolean;
  /** Fallback route for the Back button when there is no in-app history. */
  backHref?: string;
}) {
  return (
    <div className="mb-3">
      {back && <BackButton fallbackHref={backHref} className="mb-2" />}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-white">{title}</h1>
          {subtitle && <p className="mt-0.5 text-xs text-[var(--muted)]">{subtitle}</p>}
        </div>
        {action}
      </div>
    </div>
  );
}

export function TabBar({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-[var(--line)]">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onChange(t.id)}
          className={`px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide border-b-2 -mb-px transition-colors ${
            active === t.id
              ? "border-[var(--accent)] text-[var(--accent)]"
              : "border-transparent text-[var(--muted)] hover:text-white"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function StatusBadge({
  status,
}: {
  status: string;
}) {
  const s = status.toUpperCase();
  let color = "bg-[var(--panel-2)] text-[var(--muted)]";
  if (["PENDING", "OPEN", "TRIGGER PENDING", "PARTIALLY FILLED"].some((x) => s.includes(x.replace(" ", "")) || s === x)) {
    color = "bg-[var(--accent-2)]/15 text-[var(--accent-2)]";
  } else if (["TRADED", "FILLED", "PAPER_FILLED", "COMPLETE"].some((x) => s.includes(x))) {
    color = "bg-[var(--profit)]/15 text-[var(--profit)]";
  } else if (s.includes("REJECT")) {
    color = "bg-[var(--loss)]/15 text-[var(--loss)]";
  } else if (s.includes("CANCEL")) {
    color = "bg-[var(--muted)]/20 text-[var(--muted)]";
  }
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${color}`}>
      {status}
    </span>
  );
}

export function TerminalInput({
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`rounded border border-[var(--line)] bg-[var(--background)] px-2.5 py-1.5 text-xs text-white placeholder:text-[var(--muted)] focus:border-[var(--accent)] focus:outline-none ${className}`}
      {...props}
    />
  );
}

export function TerminalSelect({
  className = "",
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`rounded border border-[var(--line)] bg-[var(--background)] px-2.5 py-1.5 text-xs text-white focus:border-[var(--accent)] focus:outline-none ${className}`}
      {...props}
    >
      {children}
    </select>
  );
}

export function SummaryTile({
  label,
  value,
  sub,
  pnl,
}: {
  label: string;
  value: string;
  sub?: string;
  pnl?: number | null;
}) {
  return (
    <div className="rounded border border-[var(--line)] bg-[var(--panel-2)] px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums text-white">{value}</p>
      {pnl != null ? (
        <PnlText value={pnl} className="text-[11px]" />
      ) : sub ? (
        <p className="text-[11px] text-[var(--muted)]">{sub}</p>
      ) : null}
    </div>
  );
}

export function StatRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1 text-xs">
      <span className="text-[var(--muted)]">{label}</span>
      <span className="text-right text-white tabular-nums">{value}</span>
    </div>
  );
}
