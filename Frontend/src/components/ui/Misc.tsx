import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("shimmer rounded-md bg-surface-3", className)} />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-16 text-center", className)}>
      {icon && (
        <div className="mb-4 grid size-11 place-items-center rounded-xl border border-line bg-surface-2 text-ink-3">
          {icon}
        </div>
      )}
      <h4 className="text-[14.5px] font-semibold text-ink">{title}</h4>
      {description && (
        <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-ink-2">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** Key/value row used across evidence, transaction detail and settings. */
export function DetailRow({
  label,
  value,
  mono,
  tone,
  className,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
  tone?: "default" | "muted" | "critical";
  className?: string;
}) {
  return (
    <div className={cn("flex items-baseline justify-between gap-6 py-2.5", className)}>
      <span className="shrink-0 text-[12.5px] text-ink-2">{label}</span>
      <span
        className={cn(
          "min-w-0 truncate text-right text-[13px] font-medium",
          mono && "tnum",
          tone === "muted" ? "text-ink-3" : tone === "critical" ? "text-critical-text" : "text-ink",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function ProgressBar({
  percent,
  tone = "accent",
  height = 8,
  animated,
  className,
}: {
  percent: number;
  tone?: "accent" | "good" | "ai";
  height?: number;
  animated?: boolean;
  className?: string;
}) {
  const bg = { accent: "bg-accent", good: "bg-good", ai: "bg-ai" }[tone];
  return (
    <div
      className={cn("w-full overflow-hidden rounded-full bg-surface-3", className)}
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(percent)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn("relative h-full rounded-full", bg, animated && "shimmer")}
        style={{
          width: `${Math.min(100, Math.max(0, percent))}%`,
          transition: "width 420ms cubic-bezier(0.22, 1, 0.36, 1)",
        }}
      />
    </div>
  );
}

/** Thin, understated divider with an optional inline label. */
export function Divider({ label, className }: { label?: string; className?: string }) {
  if (!label) return <div className={cn("h-px w-full bg-line", className)} />;
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div className="h-px flex-1 bg-line" />
      <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-3">{label}</span>
      <div className="h-px flex-1 bg-line" />
    </div>
  );
}
