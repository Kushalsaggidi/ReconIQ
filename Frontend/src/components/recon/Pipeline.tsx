import { ArrowRight, Cpu, Database, FileCheck2, Scale, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The product's architecture, stated plainly:
 *   data -> deterministic reconciliation -> matched/exceptions -> AI explanation -> auditable result
 * The AI step is visually the odd one out on purpose — it explains, it does not compute.
 */
const STAGES = [
  {
    key: "data",
    label: "Source data",
    detail: "Orders · Settlements · Bank",
    icon: Database,
    engine: "deterministic" as const,
  },
  {
    key: "recon",
    label: "Deterministic reconciliation",
    detail: "Matching, variance, calculations",
    icon: Cpu,
    engine: "deterministic" as const,
  },
  {
    key: "split",
    label: "Matched / exceptions",
    detail: "Every figure computed, not inferred",
    icon: Scale,
    engine: "deterministic" as const,
  },
  {
    key: "ai",
    label: "AI explanation",
    detail: "Classification & reasoning only",
    icon: Sparkles,
    engine: "ai" as const,
  },
  {
    key: "audit",
    label: "Auditable result",
    detail: "Traceable, exportable, signed",
    icon: FileCheck2,
    engine: "deterministic" as const,
  },
];

export function PipelineStrip({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-line bg-surface p-5 shadow-xs", className)}>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[13px] font-semibold tracking-[-0.01em] text-ink">How a result is produced</h3>
        <p className="text-[12px] text-ink-2">
          A reconciliation engine with{" "}
          <span className="font-medium text-ai-text">AI-assisted exception analysis</span> — not an AI that does
          finance.
        </p>
      </div>

      <ol className="flex flex-col gap-2 lg:flex-row lg:items-stretch lg:gap-0">
        {STAGES.map((s, i) => (
          <li key={s.key} className="flex min-w-0 flex-1 items-center gap-2">
            <div
              className={cn(
                "min-w-0 flex-1 rounded-lg border px-3 py-2.5 transition-colors duration-150",
                s.engine === "ai"
                  ? "border-ai-line bg-ai-soft"
                  : "border-line bg-surface-2 hover:border-line-strong",
              )}
            >
              <div className="flex items-center gap-2">
                <s.icon
                  className={cn("size-3.5 shrink-0", s.engine === "ai" ? "text-ai" : "text-accent")}
                  strokeWidth={2.25}
                />
                <span
                  className={cn(
                    "truncate text-[12px] font-semibold",
                    s.engine === "ai" ? "text-ai-text" : "text-ink",
                  )}
                >
                  {s.label}
                </span>
              </div>
              <p className="mt-1 truncate text-[11.5px] text-ink-3">{s.detail}</p>
            </div>
            {i < STAGES.length - 1 && (
              <ArrowRight className="hidden size-3.5 shrink-0 text-ink-3 lg:block" strokeWidth={2.5} />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

const STEPS = [
  { label: "Upload data", detail: "Orders, settlements, bank" },
  { label: "Validate", detail: "Schema & integrity checks" },
  { label: "Reconcile", detail: "Deterministic matching" },
  { label: "Analyze exceptions", detail: "AI classification", ai: true },
  { label: "Generate report", detail: "Audit trail & export" },
];

export function HowItWorks() {
  return (
    <div className="rounded-xl border border-line bg-surface-2 px-5 py-5">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h3 className="text-[12.5px] font-semibold text-ink">How it works</h3>
        <span className="text-[11.5px] text-ink-3">Typically completes in under 15 seconds</span>
      </div>
      <ol className="flex flex-col gap-3 sm:flex-row sm:items-start sm:gap-0">
        {STEPS.map((s, i) => (
          <li key={s.label} className="flex min-w-0 flex-1 items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "tnum grid size-5 shrink-0 place-items-center rounded-full text-[10.5px] font-semibold",
                    s.ai
                      ? "bg-ai-soft text-ai-text ring-1 ring-ai-line"
                      : "bg-surface text-ink-2 ring-1 ring-line-strong",
                  )}
                >
                  {i + 1}
                </span>
                <span className={cn("truncate text-[12.5px] font-medium", s.ai ? "text-ai-text" : "text-ink")}>
                  {s.label}
                </span>
              </div>
              <p className="mt-1 pl-7 text-[11.5px] leading-relaxed text-ink-3 sm:pl-0">{s.detail}</p>
            </div>
            {i < STEPS.length - 1 && (
              <div className="mt-2.5 hidden h-px w-6 shrink-0 bg-line-strong sm:block" aria-hidden />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
