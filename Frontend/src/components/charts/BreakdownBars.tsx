import { cn, formatCrore, formatNumber } from "@/lib/utils";
import type { ExceptionBucket, ExceptionType } from "@/services/types";

/**
 * Exception buckets, ranked. Color carries one distinction only — whether the
 * engine could account for the variance — so the palette stays at two roles
 * and the axis labels carry identity.
 */
export function BreakdownBars({
  buckets,
  onSelect,
  selected,
  showAmount = true,
}: {
  buckets: ExceptionBucket[];
  onSelect?: (type: ExceptionType) => void;
  selected?: ExceptionType | null;
  showAmount?: boolean;
}) {
  const max = Math.max(...buckets.map((b) => b.count), 1);
  const totalCount = buckets.reduce((a, b) => a + b.count, 0);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2">
        <LegendItem swatch="bg-accent" label="Explained by a record" />
        <LegendItem swatch="bg-critical" label="No supporting record — human review" />
      </div>

      <ul className="space-y-3.5">
        {buckets.map((b) => {
          const pct = (b.count / max) * 100;
          const share = (b.count / totalCount) * 100;
          const isSel = selected === b.type;
          const interactive = Boolean(onSelect);
          return (
            <li key={b.type}>
              <button
                type="button"
                disabled={!interactive}
                onClick={() => onSelect?.(b.type)}
                className={cn(
                  "group block w-full rounded-lg px-2 py-1.5 text-left transition-colors duration-150",
                  interactive && "hover:bg-surface-2",
                  isSel && "bg-accent-soft",
                  !interactive && "cursor-default",
                )}
              >
                <div className="flex items-baseline justify-between gap-4">
                  <span className="flex items-center gap-2 text-[13px] font-medium text-ink">
                    {b.label}
                    {!b.autoExplained && (
                      <span className="rounded border border-critical-line bg-critical-soft px-1.5 py-px text-[10.5px] font-semibold uppercase tracking-wide text-critical-text">
                        review
                      </span>
                    )}
                  </span>
                  <span className="flex shrink-0 items-baseline gap-2">
                    <span className="tnum text-[14px] font-semibold text-ink">{formatNumber(b.count)}</span>
                    <span className="tnum w-11 text-right text-[11.5px] text-ink-3">{share.toFixed(1)}%</span>
                  </span>
                </div>

                <div className="mt-2 flex items-center gap-3">
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-3">
                    <div
                      className={cn(
                        "h-full rounded-full transition-[width,filter] duration-[700ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                        b.autoExplained ? "bg-accent" : "bg-critical",
                        interactive && "group-hover:brightness-110",
                      )}
                      style={{ width: `${Math.max(pct, 1.5)}%` }}
                    />
                  </div>
                  {showAmount && (
                    <span className="tnum w-20 shrink-0 text-right text-[11.5px] text-ink-3">
                      {formatCrore(b.amount)}
                    </span>
                  )}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function LegendItem({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-[11.5px] text-ink-2">
      <span className={cn("h-2 w-4 rounded-full", swatch)} />
      {label}
    </span>
  );
}
