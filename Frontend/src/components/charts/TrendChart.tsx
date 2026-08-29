import { useMemo, useState } from "react";
import { cn, formatNumber } from "@/lib/utils";
import type { TrendPoint } from "@/services/types";
import { useMeasure } from "./useMeasure";

/**
 * Match rate over the last 14 batches.
 *
 * One measure, one axis. Volume and exception counts live in the tooltip
 * rather than on a second y-scale.
 */
export function TrendChart({ data, height = 232 }: { data: TrendPoint[]; height?: number }) {
  const { ref, width } = useMeasure<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);

  const pad = { top: 16, right: 16, bottom: 26, left: 44 };
  const w = Math.max(width, 320);
  const innerW = w - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const { min, max, ticks } = useMemo(() => {
    const values = data.map((d) => d.matchRate);
    const lo = Math.floor(Math.min(...values) - 0.8);
    const hi = Math.min(100, Math.ceil(Math.max(...values) + 0.4));
    const step = (hi - lo) / 4;
    return {
      min: lo,
      max: hi,
      ticks: Array.from({ length: 5 }, (_, i) => Number((lo + step * i).toFixed(1))),
    };
  }, [data]);

  const x = (i: number) => (data.length <= 1 ? 0 : (i / (data.length - 1)) * innerW);
  const y = (v: number) => innerH - ((v - min) / (max - min)) * innerH;

  const line = data.map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(d.matchRate).toFixed(1)}`).join(" ");
  const area = `${line} L${x(data.length - 1).toFixed(1)},${innerH} L0,${innerH} Z`;

  const active = hover !== null ? data[hover] : null;
  const target = 97;

  return (
    <div ref={ref} className="relative w-full select-none">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${w} ${height}`}
        role="img"
        aria-label="Match rate over the last fourteen reconciliation batches"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const scale = w / rect.width;
          const px = (e.clientX - rect.left) * scale - pad.left;
          const i = Math.round((px / innerW) * (data.length - 1));
          setHover(Math.max(0, Math.min(data.length - 1, i)));
        }}
      >
        <defs>
          <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.16" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.01" />
          </linearGradient>
        </defs>

        <g transform={`translate(${pad.left},${pad.top})`}>
          {/* recessive gridlines + axis labels */}
          {ticks.map((t) => (
            <g key={t}>
              <line x1={0} x2={innerW} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={1} />
              <text
                x={-10}
                y={y(t)}
                dy="0.32em"
                textAnchor="end"
                className="tnum"
                fontSize={10.5}
                fill="var(--ink-3)"
              >
                {t.toFixed(1)}%
              </text>
            </g>
          ))}

          {/* SLA reference — labelled, so the line is never a mystery */}
          {target > min && target < max && (
            <g>
              <line
                x1={0}
                x2={innerW}
                y1={y(target)}
                y2={y(target)}
                stroke="var(--line-strong)"
                strokeWidth={1}
                strokeDasharray="3 3"
              />
              <text x={innerW} y={y(target) - 6} textAnchor="end" fontSize={10} fill="var(--ink-3)">
                Target 97.0%
              </text>
            </g>
          )}

          <path d={area} fill="url(#trend-fill)" />
          <path
            d={line}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* last point is always marked — it is the batch on screen */}
          <circle
            cx={x(data.length - 1)}
            cy={y(data[data.length - 1].matchRate)}
            r={4}
            fill="var(--accent)"
            stroke="var(--surface)"
            strokeWidth={2}
          />

          {hover !== null && (
            <g>
              <line
                x1={x(hover)}
                x2={x(hover)}
                y1={0}
                y2={innerH}
                stroke="var(--line-strong)"
                strokeWidth={1}
              />
              <circle
                cx={x(hover)}
                cy={y(data[hover].matchRate)}
                r={5}
                fill="var(--accent)"
                stroke="var(--surface)"
                strokeWidth={2}
              />
            </g>
          )}

          {/* x labels — every third tick to avoid collisions */}
          {data.map((d, i) =>
            i % 3 === 0 || i === data.length - 1 ? (
              <text
                key={d.date}
                x={x(i)}
                y={innerH + 17}
                textAnchor={i === data.length - 1 ? "end" : i === 0 ? "start" : "middle"}
                fontSize={10.5}
                fill="var(--ink-3)"
              >
                {d.label}
              </text>
            ) : null,
          )}

          <line x1={0} x2={innerW} y1={innerH} y2={innerH} stroke="var(--line-strong)" strokeWidth={1} />
        </g>
      </svg>

      {active && hover !== null && (
        <div
          className="pointer-events-none absolute z-10 w-[196px] rounded-lg border border-line bg-surface p-3 shadow-md"
          style={{
            left: Math.min(Math.max(0, (x(hover) + pad.left) * (width / w) - 98), Math.max(0, width - 196)),
            top: 4,
          }}
        >
          <div className="text-[12px] font-semibold text-ink">{active.label}</div>
          <div className="mt-2 space-y-1.5">
            <Row label="Match rate" value={`${active.matchRate.toFixed(2)}%`} strong />
            <Row label="Processed" value={formatNumber(active.processed)} />
            <Row label="Matched" value={formatNumber(active.matched)} />
            <Row label="Exceptions" value={formatNumber(active.exceptions)} />
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[11.5px] text-ink-2">{label}</span>
      <span className={cn("tnum text-[12px]", strong ? "font-semibold text-ink" : "text-ink-2")}>{value}</span>
    </div>
  );
}
