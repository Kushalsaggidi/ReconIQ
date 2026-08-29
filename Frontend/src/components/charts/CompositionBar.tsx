import { useState } from "react";
import { cn, formatNumber } from "@/lib/utils";

export interface Segment {
  key: string;
  label: string;
  value: number;
  /** Status roles only — this chart encodes state, not identity. */
  tone: "good" | "serious" | "critical";
}

const FILL = {
  good: "var(--good)",
  serious: "var(--serious)",
  critical: "var(--critical)",
};

const TEXT = {
  good: "text-good-text",
  serious: "text-serious-text",
  critical: "text-critical-text",
};

/**
 * One stacked bar for the whole batch: matched / exception / unresolved.
 * 2px surface gaps between segments, legend plus direct labels, so identity
 * never rests on color alone.
 */
export function CompositionBar({
  segments,
  total,
  height = 14,
}: {
  segments: Segment[];
  total: number;
  height?: number;
}) {
  const [hover, setHover] = useState<string | null>(null);

  return (
    <div>
      <div
        className="flex w-full overflow-hidden rounded-full bg-surface-3"
        style={{ height }}
        onMouseLeave={() => setHover(null)}
      >
        {segments.map((s, i) => {
          const pct = (s.value / total) * 100;
          return (
            <div
              key={s.key}
              onMouseEnter={() => setHover(s.key)}
              title={`${s.label}: ${formatNumber(s.value)} (${pct.toFixed(2)}%)`}
              className="h-full transition-[opacity,transform] duration-200"
              style={{
                width: `${Math.max(pct, 0.35)}%`,
                background: FILL[s.tone],
                marginLeft: i === 0 ? 0 : 2,
                opacity: hover && hover !== s.key ? 0.45 : 1,
              }}
            />
          );
        })}
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        {segments.map((s) => {
          const pct = (s.value / total) * 100;
          return (
            <div
              key={s.key}
              onMouseEnter={() => setHover(s.key)}
              onMouseLeave={() => setHover(null)}
              className={cn(
                "rounded-lg border border-line bg-surface-2 px-4 py-3 transition-colors duration-150",
                hover === s.key && "border-line-strong bg-surface-3",
              )}
            >
              <div className="flex items-center gap-2">
                <span className="size-2 rounded-full" style={{ background: FILL[s.tone] }} />
                <span className="text-[12.5px] font-medium text-ink-2">{s.label}</span>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="tnum text-[21px] font-semibold tracking-[-0.02em] text-ink">
                  {formatNumber(s.value)}
                </span>
                <span className={cn("tnum text-[12px] font-medium", TEXT[s.tone])}>{pct.toFixed(2)}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
