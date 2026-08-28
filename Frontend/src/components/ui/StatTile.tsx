import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { CountUp } from "./CountUp";

export interface StatTileProps {
  label: string;
  value: number;
  format: (n: number) => string;
  /** Small supporting line under the figure — units, denominator, share. */
  support?: ReactNode;
  delta?: { value: number; label: string; direction: "up" | "down" | "flat"; good: boolean };
  icon?: ReactNode;
  /** A thin rule under the figure carrying this share of the tile width. */
  meter?: { fraction: number; tone: "accent" | "good" | "serious" | "critical" };
  emphasis?: boolean;
  className?: string;
  footer?: ReactNode;
}

const METER_BG = {
  accent: "bg-accent",
  good: "bg-good",
  serious: "bg-serious",
  critical: "bg-critical",
};

export function StatTile({
  label,
  value,
  format,
  support,
  delta,
  icon,
  meter,
  emphasis,
  className,
  footer,
}: StatTileProps) {
  return (
    <div
      className={cn(
        "card-hover relative flex flex-col rounded-xl border bg-surface p-5 shadow-xs",
        emphasis ? "border-accent-soft-line bg-accent-soft/40" : "border-line",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <span className="text-[12.5px] font-medium tracking-[0.01em] text-ink-2">{label}</span>
        {icon && (
          <span
            className={cn(
              "grid size-7 shrink-0 place-items-center rounded-md",
              emphasis ? "bg-accent text-accent-ink" : "bg-surface-3 text-ink-2",
            )}
          >
            {icon}
          </span>
        )}
      </div>

      <div className="mt-3 flex items-baseline gap-2">
        <CountUp
          value={value}
          format={format}
          className={cn(
            "font-semibold tracking-[-0.03em] text-ink",
            emphasis ? "text-[34px] leading-none" : "text-[28px] leading-none",
          )}
        />
        {delta && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 text-[12px] font-medium",
              delta.direction === "flat" ? "text-ink-3" : delta.good ? "text-good-text" : "text-critical-text",
            )}
          >
            {delta.direction === "up" ? (
              <ArrowUpRight className="size-3.5" strokeWidth={2.5} />
            ) : delta.direction === "down" ? (
              <ArrowDownRight className="size-3.5" strokeWidth={2.5} />
            ) : (
              <Minus className="size-3.5" strokeWidth={2.5} />
            )}
            {delta.label}
          </span>
        )}
      </div>

      {support && <p className="mt-2 text-[12.5px] leading-relaxed text-ink-3">{support}</p>}

      {meter && (
        <div className="mt-4 h-1 overflow-hidden rounded-full bg-surface-3">
          <div
            className={cn("h-full rounded-full transition-[width] duration-[900ms] ease-[cubic-bezier(0.22,1,0.36,1)]", METER_BG[meter.tone])}
            style={{ width: `${Math.max(1.5, meter.fraction * 100)}%` }}
          />
        </div>
      )}

      {footer && <div className="mt-4 border-t border-line pt-3">{footer}</div>}
    </div>
  );
}
