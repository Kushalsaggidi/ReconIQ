import type { ReactNode } from "react";
import { AlertTriangle, Check, CircleDot, Cpu, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Confidence, ExceptionType, TxnStatus } from "@/services/types";

type Tone = "neutral" | "accent" | "good" | "warning" | "serious" | "critical" | "ai";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-3 text-ink-2 border-line",
  accent: "bg-accent-soft text-accent-text border-accent-soft-line",
  good: "bg-good-soft text-good-text border-good-line",
  warning: "bg-warning-soft text-warning-text border-warning-line",
  serious: "bg-serious-soft text-serious-text border-serious-line",
  critical: "bg-critical-soft text-critical-text border-critical-line",
  ai: "bg-ai-soft text-ai-text border-ai-line",
};

export function Badge({
  children,
  tone = "neutral",
  icon,
  className,
  size = "md",
}: {
  children: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
  className?: string;
  size?: "sm" | "md";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border font-medium whitespace-nowrap",
        size === "sm" ? "px-1.5 py-0.5 text-[11px]" : "px-2 py-[3px] text-[12px]",
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/** Status never travels on color alone — every state ships an icon + label. */
export function StatusBadge({ status, size = "md" }: { status: TxnStatus; size?: "sm" | "md" }) {
  if (status === "matched")
    return (
      <Badge tone="good" size={size} icon={<Check className="size-3.5" strokeWidth={2.75} />}>
        Matched
      </Badge>
    );
  if (status === "exception")
    return (
      <Badge tone="serious" size={size} icon={<AlertTriangle className="size-3.5" strokeWidth={2.5} />}>
        Exception
      </Badge>
    );
  return (
    <Badge tone="critical" size={size} icon={<X className="size-3.5" strokeWidth={3} />}>
      Unresolved
    </Badge>
  );
}

export function ExceptionTypeBadge({ type }: { type: ExceptionType | null }) {
  if (!type) return <span className="text-ink-3">—</span>;
  const label = {
    partial_payment: "Partial Payment",
    refund: "Refund",
    fee_tax: "Fee / Tax",
    rounding: "Rounding",
    unresolved: "Unresolved",
  }[type];
  return (
    <Badge tone={type === "unresolved" ? "critical" : "neutral"} size="sm">
      {label}
    </Badge>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const map = {
    high: { tone: "good" as Tone, label: "Confidence: High" },
    medium: { tone: "warning" as Tone, label: "Confidence: Medium" },
    low: { tone: "critical" as Tone, label: "Confidence: Low" },
  }[confidence];
  return (
    <Badge tone={map.tone} icon={<CircleDot className="size-3.5" />}>
      {map.label}
    </Badge>
  );
}

/**
 * The single most important visual distinction in the product: which layer
 * produced a figure. Deterministic engine vs. AI analyst, labelled explicitly.
 */
export function EngineBadge({
  engine,
  className,
}: {
  engine: "deterministic" | "ai" | "system";
  className?: string;
}) {
  if (engine === "ai")
    return (
      <Badge tone="ai" className={className} icon={<Sparkles className="size-3.5" />}>
        AI analysis
      </Badge>
    );
  if (engine === "system")
    return (
      <Badge tone="neutral" className={className} icon={<CircleDot className="size-3.5" />}>
        System
      </Badge>
    );
  return (
    <Badge tone="accent" className={className} icon={<Cpu className="size-3.5" />}>
      Deterministic engine
    </Badge>
  );
}

export function Dot({ tone }: { tone: Tone }) {
  const bg: Record<Tone, string> = {
    neutral: "bg-ink-3",
    accent: "bg-accent",
    good: "bg-good",
    warning: "bg-warning",
    serious: "bg-serious",
    critical: "bg-critical",
    ai: "bg-ai",
  };
  return <span className={cn("size-2 shrink-0 rounded-full", bg[tone])} />;
}
