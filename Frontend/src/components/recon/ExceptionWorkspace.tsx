import { motion } from "framer-motion";
import {
  ArrowRight,
  Ban,
  Calculator,
  Check,
  CircleSlash,
  Cpu,
  Database,
  FileText,
  Info,
  Sparkles,
  X,
} from "lucide-react";
import { cn, formatDate, formatMoney } from "@/lib/utils";
import { Badge, ConfidenceBadge, StatusBadge } from "@/components/ui/Badge";
import { DetailRow, Divider } from "@/components/ui/Misc";
import { exceptionTypeLabel } from "@/services/analysis";
import type { ExceptionDetail } from "@/services/types";

/**
 * The investigation workspace.
 *
 * Reading order is deliberate: the engine's arithmetic first, the AI's
 * interpretation second, the source records third. Every AI element sits on the
 * violet AI surface; every computed figure sits on a neutral surface with the
 * "computed by the engine" attribution.
 */
export function ExceptionWorkspace({ detail }: { detail: ExceptionDetail }) {
  const { transaction: t, computed, ai, evidence } = detail;

  return (
    <div className="divide-y divide-line">
      {/* ---------------- financial comparison — computed ---------------- */}
      <section className="px-6 py-6">
        <SectionLabel
          icon={<Calculator className="size-3.5" />}
          title="Financial comparison"
          note="Computed by the deterministic engine"
          engine="deterministic"
        />

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <AmountCell label="Expected amount" value={formatMoney(computed.expected)} sub="From the orders dataset" />
          <AmountCell
            label="Actual settlement"
            value={formatMoney(computed.settled)}
            sub={t.settlementId ? "From the settlement record" : "No settlement row found"}
          />
          <AmountCell
            label="Difference"
            value={formatMoney(-computed.difference, { signed: true })}
            sub={computed.unexplained === 0 ? "Fully accounted for" : "Short of the expected amount"}
            tone={computed.difference === 0 ? "neutral" : computed.unexplained > 0 ? "critical" : "serious"}
            emphasis
          />
        </div>

        {/* variance decomposition — arithmetic, shown as arithmetic */}
        <div className="mt-4 rounded-lg border border-line bg-surface-2 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <span className="text-[12px] font-semibold text-ink">Variance decomposition</span>
            <span className="text-[11.5px] text-ink-3">All figures derived from the source records</span>
          </div>
          <div className="divide-y divide-line">
            <DetailRow label="Platform fee" value={formatMoney(t.fee)} mono tone={t.fee ? "default" : "muted"} />
            <DetailRow label="Tax (GST 18%)" value={formatMoney(t.tax)} mono tone={t.tax ? "default" : "muted"} />
            <DetailRow
              label="Refund ledger"
              value={t.refund ? formatMoney(t.refund) : "No entry found"}
              mono={Boolean(t.refund)}
              tone={t.refund ? "default" : "muted"}
            />
            <DetailRow
              label="Accounted for by records"
              value={formatMoney(computed.accountedFor)}
              mono
            />
            <DetailRow
              label="Unexplained variance"
              value={formatMoney(computed.unexplained)}
              mono
              tone={computed.unexplained > 0 ? "critical" : "default"}
              className="font-semibold"
            />
          </div>
        </div>

        {/* checks */}
        <ul className="mt-4 space-y-2">
          {computed.checks.map((c) => (
            <li key={c.label} className="flex items-start gap-2.5">
              <span
                className={cn(
                  "mt-px grid size-4.5 shrink-0 place-items-center rounded-full",
                  c.passed ? "bg-good-soft text-good-text" : "bg-critical-soft text-critical-text",
                )}
              >
                {c.passed ? <Check className="size-3" strokeWidth={3} /> : <X className="size-3" strokeWidth={3} />}
              </span>
              <div className="min-w-0">
                <span className="text-[12.5px] font-medium text-ink">{c.label}</span>
                <span className="ml-1.5 text-[12.5px] text-ink-2">— {c.detail}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* ---------------- transaction details ---------------- */}
      <section className="px-6 py-6">
        <SectionLabel icon={<FileText className="size-3.5" />} title="Transaction details" />
        <div className="mt-3 grid gap-x-8 sm:grid-cols-2">
          <div className="divide-y divide-line">
            <DetailRow label="Order ID" value={t.orderId} mono />
            <DetailRow label="Payment ID" value={t.paymentId} mono />
            <DetailRow label="Settlement ID" value={t.settlementId ?? "Not found"} mono={Boolean(t.settlementId)} tone={t.settlementId ? "default" : "critical"} />
            <DetailRow label="Bank reference" value={t.bankRef ?? "Not found"} mono={Boolean(t.bankRef)} tone={t.bankRef ? "default" : "critical"} />
          </div>
          <div className="divide-y divide-line">
            <DetailRow label="Settlement date" value={formatDate(t.settlementDate)} />
            <DetailRow label="Payment method" value={t.method} />
            <DetailRow label="Fee" value={formatMoney(t.fee)} mono />
            <DetailRow label="Tax" value={formatMoney(t.tax)} mono />
            <DetailRow label="Refund" value={t.refund ? formatMoney(t.refund) : "—"} mono={Boolean(t.refund)} tone={t.refund ? "default" : "muted"} />
          </div>
        </div>
      </section>

      {/* ---------------- AI analysis ---------------- */}
      <section className="px-6 py-6">
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="overflow-hidden rounded-xl border border-ai-line bg-ai-soft"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ai-line px-5 py-3.5">
            <div className="flex items-center gap-2.5">
              <span className="grid size-7 place-items-center rounded-lg bg-ai text-white">
                <Sparkles className="size-4" strokeWidth={2.25} />
              </span>
              <div>
                <h4 className="text-[14px] font-semibold tracking-[-0.01em] text-ai-text">AI Analysis</h4>
                <p className="text-[11px] text-ai-text/80">Classification and explanation only</p>
              </div>
            </div>
            <ConfidenceBadge confidence={ai.confidence} />
          </div>

          <div className="px-5 py-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11.5px] font-medium text-ai-text/80">Classification</span>
              <Badge tone={ai.confidence === "low" ? "critical" : "ai"}>{ai.classification}</Badge>
            </div>

            <p className="mt-3.5 text-[13.5px] leading-[1.65] text-ink">{ai.explanation}</p>

            <div className="mt-4">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-ai-text/80">
                Signals considered
              </p>
              <ul className="space-y-1.5">
                {ai.signals.map((s) => (
                  <li key={s} className="flex items-start gap-2 text-[12.5px] leading-relaxed text-ink-2">
                    <ArrowRight className="mt-[3px] size-3 shrink-0 text-ai" strokeWidth={2.5} />
                    {s}
                  </li>
                ))}
              </ul>
            </div>

            {/* the guardrail, stated on the card itself */}
            <div className="mt-4 flex items-start gap-2 rounded-lg border border-ai-line bg-surface/60 px-3.5 py-2.5">
              <Info className="mt-px size-3.5 shrink-0 text-ai" />
              <p className="text-[11.5px] leading-relaxed text-ink-2">
                The model did not calculate any amount on this page. Every figure above was computed by the
                deterministic engine from the source records; the model only labelled and explained the variance.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ai-line px-5 py-2.5">
            <span className="text-[11px] text-ai-text/80">{ai.model}</span>
            <span className="tnum text-[11px] text-ai-text/80">{ai.tokens} tokens · no autonomous action taken</span>
          </div>
        </motion.div>
      </section>

      {/* ---------------- evidence ---------------- */}
      <section className="px-6 py-6">
        <SectionLabel
          icon={<Database className="size-3.5" />}
          title="Evidence"
          note="The exact records this decision was made from"
        />
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {evidence.map((rec) => (
            <div
              key={rec.source}
              className={cn(
                "rounded-lg border p-4",
                rec.present ? "border-line bg-surface-2" : "border-critical-line bg-critical-soft/40",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold text-ink">{rec.source}</p>
                  <p className="tnum mt-0.5 truncate text-[11.5px] text-ink-3">{rec.recordId}</p>
                </div>
                {rec.present ? (
                  <Badge tone="good" size="sm" icon={<Check className="size-3" strokeWidth={3} />}>
                    found
                  </Badge>
                ) : (
                  <Badge tone="critical" size="sm" icon={<CircleSlash className="size-3" strokeWidth={2.5} />}>
                    missing
                  </Badge>
                )}
              </div>
              <div className="mt-2 divide-y divide-line">
                {rec.fields.map((f) => (
                  <DetailRow
                    key={f.label}
                    label={f.label}
                    value={f.value}
                    mono={f.emphasis}
                    className={cn("py-2", f.emphasis && "font-semibold")}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ---------------- recommended action ---------------- */}
      <section className="px-6 py-6">
        <SectionLabel icon={<Cpu className="size-3.5" />} title="Recommended action" />
        <div className="mt-3 rounded-lg border border-line bg-surface-2 p-4">
          <div className="flex items-start gap-3">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-surface text-ink-2 ring-1 ring-line">
              <ArrowRight className="size-4" strokeWidth={2.25} />
            </span>
            <div className="min-w-0">
              <p className="text-[13.5px] font-medium text-ink">{ai.recommendedAction}</p>
              <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">
                {t.status === "unresolved"
                  ? "No value was inferred and no ledger was adjusted. This record stays open until a reviewer resolves it."
                  : "The variance is explained by a record in the batch. Approving here only marks the exception reviewed — it makes no financial change."}
              </p>
            </div>
          </div>

          <Divider className="my-4" />

          <div className="flex items-center gap-2 text-[11.5px] text-ink-3">
            <Ban className="size-3.5 shrink-0" />
            The application never posts, adjusts or reverses a transaction. Reconciliation is read-only by design.
          </div>
        </div>
      </section>
    </div>
  );
}

function SectionLabel({
  icon,
  title,
  note,
  engine,
}: {
  icon: React.ReactNode;
  title: string;
  note?: string;
  engine?: "deterministic" | "ai";
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h4 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-3">
        <span className="text-ink-3">{icon}</span>
        {title}
      </h4>
      {note && (
        <span
          className={cn(
            "text-[11.5px]",
            engine === "deterministic" ? "font-medium text-accent-text" : "text-ink-3",
          )}
        >
          {note}
        </span>
      )}
    </div>
  );
}

/** Big three-up amount comparison. */
function AmountCell({
  label,
  value,
  sub,
  tone = "neutral",
  emphasis,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "neutral" | "serious" | "critical";
  emphasis?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border px-4 py-3.5",
        tone === "critical"
          ? "border-critical-line bg-critical-soft"
          : tone === "serious"
            ? "border-serious-line bg-serious-soft"
            : "border-line bg-surface-2",
      )}
    >
      <p className="text-[11.5px] font-medium text-ink-2">{label}</p>
      <p
        className={cn(
          "tnum mt-1.5 font-semibold tracking-[-0.02em]",
          emphasis ? "text-[22px]" : "text-[20px]",
          tone === "critical" ? "text-critical-text" : tone === "serious" ? "text-serious-text" : "text-ink",
        )}
      >
        {value}
      </p>
      <p className="mt-1 text-[11.5px] leading-relaxed text-ink-3">{sub}</p>
    </div>
  );
}

/** Compact header used by both the drawer and the standalone page. */
export function ExceptionHeaderMeta({ detail }: { detail: ExceptionDetail }) {
  const { transaction: t } = detail;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <StatusBadge status={t.status} />
      <Badge tone="neutral" size="sm">
        {exceptionTypeLabel(t)}
      </Badge>
      <span className="text-[12px] text-ink-3">Settled {formatDate(t.settlementDate)}</span>
    </div>
  );
}
