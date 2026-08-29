import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowRight, Search, Sparkles } from "lucide-react";
import { formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, SectionHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/Misc";
import { BreakdownBars } from "@/components/charts/BreakdownBars";
import { TransactionTable } from "@/components/recon/TransactionTable";
import { ExceptionDrawer } from "@/components/recon/ExceptionDrawer";
import { useRecon } from "@/store/ReconProvider";
import { EXCEPTION_LABELS } from "@/services/api";

import type { ExceptionType, Transaction } from "@/services/types";

export function Exceptions() {
  const { summary } = useRecon();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [active, setActive] = useState<Transaction | null>(null);

  const typeParam = params.get("type") as ExceptionType | null;
  const type: ExceptionType | "all" =
    typeParam && typeParam in EXCEPTION_LABELS ? typeParam : "all";
  const q = params.get("q") ?? "";

  const setType = (next: ExceptionType | "all") => {
    const p = new URLSearchParams(params);
    if (next === "all") p.delete("type");
    else p.set("type", next);
    setParams(p, { replace: true });
  };

  if (!summary) {
    return (
      <Card>
        <EmptyState
          icon={<AlertTriangle className="size-5" />}
          title="No reconciliation job loaded"
          description="Run a reconciliation to see its exception queue."
          action={<Button onClick={() => navigate("/new")}>New Reconciliation</Button>}
        />
      </Card>
    );
  }

  const explained = summary.exceptions - summary.unresolved;

  return (
    <div className="space-y-7">
      <SectionHeader
        eyebrow="Exception queue"
        title="Exceptions"
        description="Every record the engine could not close on its own. Classification and reasoning come from the model; every amount comes from the engine."
      />

      {/* ---------------- summary strip ---------------- */}
      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Breakdown by category"
            description={`${formatNumber(explained)} of ${formatNumber(summary.exceptions)} exceptions were explained by a record in the batch.`}
            actions={
              type !== "all" ? (
                <Button variant="ghost" size="sm" onClick={() => setType("all")}>
                  Clear filter
                </Button>
              ) : undefined
            }
          />
          <CardBody>
            <BreakdownBars
              buckets={summary.buckets}
              selected={type === "all" ? null : type}
              onSelect={(t) => setType(type === t ? "all" : t)}
            />
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card className="border-critical-line bg-critical-soft/40">
            <CardBody className="p-5">
              <div className="flex items-center gap-2">
                <AlertTriangle className="size-4 text-critical" />
                <span className="text-[12.5px] font-semibold text-ink">Held for human review</span>
              </div>
              <p className="tnum mt-2.5 text-[30px] font-semibold leading-none tracking-[-0.03em] text-ink">
                {formatNumber(summary.unresolved)}
              </p>
              <p className="mt-2.5 text-[12.5px] leading-relaxed text-ink-2">
                No refund, fee, tax or rounding record accounts for the variance. The engine stops here rather than
                guessing, and the model is not permitted to infer a value.
              </p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-4 w-full"
                onClick={() => setType("unresolved")}
              >
                Review unresolved
                <ArrowRight className="size-3.5" />
              </Button>
            </CardBody>
          </Card>

          <Card>
            <CardBody className="p-5">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-ai" />
                <span className="text-[12.5px] font-semibold text-ink">Classifier coverage</span>
              </div>
              <div className="mt-3 space-y-2.5">
                <CoverageRow label="Explained with high confidence" value={2_186} total={summary.exceptions} tone="good" />
                <CoverageRow label="Explained, medium confidence" value={304} total={summary.exceptions} tone="warning" />
                <CoverageRow label="Returned as unresolved" value={summary.unresolved} total={summary.exceptions} tone="critical" />
              </div>
            </CardBody>
          </Card>
        </div>
      </section>

      {/* ---------------- queue ---------------- */}
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-[15px] font-semibold tracking-[-0.015em] text-ink">
            Exception queue
            <span className="tnum ml-2 text-[13px] font-normal text-ink-3">
              {formatNumber(summary.exceptions)} records
            </span>
          </h3>
          {type !== "all" && (
            <Badge tone="accent" size="sm">
              Filtered: {EXCEPTION_LABELS[type]}
            </Badge>
          )}
        </div>

        <TransactionTable
          jobId={summary.jobId}
          exceptionsOnly
          onOpen={setActive}
          activeOrderId={active?.orderId ?? null}
          initialType={type}
          initialSearch={q}
        />
      </section>

      <p className="flex items-center justify-center gap-2 text-center text-[12px] text-ink-3">
        <Search className="size-3.5" />
        Tip: press ⌘K and enter an order ID to jump straight to a case.
      </p>

      <ExceptionDrawer jobId={summary.jobId} transaction={active} onClose={() => setActive(null)} />
    </div>
  );
}

function CoverageRow({
  label,
  value,
  total,
  tone,
}: {
  label: string;
  value: number;
  total: number;
  tone: "good" | "warning" | "critical";
}) {
  const pct = (value / total) * 100;
  const bg = { good: "bg-good", warning: "bg-warning", critical: "bg-critical" }[tone];
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[12px] text-ink-2">{label}</span>
        <span className="tnum text-[12px] font-medium text-ink">{formatNumber(value)}</span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div
          className={`h-full rounded-full ${bg} transition-[width] duration-700 ease-[cubic-bezier(0.22,1,0.36,1)]`}
          style={{ width: `${Math.max(pct, 1)}%` }}
        />
      </div>
    </div>
  );
}
