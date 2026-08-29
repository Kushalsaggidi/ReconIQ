import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileClock,
  Layers,
  PartyPopper,
  Target,
} from "lucide-react";
import { formatCrore, formatDateTime, formatNumber, formatPercent } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader, SectionHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { CompositionBar } from "@/components/charts/CompositionBar";
import { BreakdownBars } from "@/components/charts/BreakdownBars";
import { TransactionTable } from "@/components/recon/TransactionTable";
import { ExceptionDrawer } from "@/components/recon/ExceptionDrawer";
import { Skeleton } from "@/components/ui/Misc";
import * as api from "@/services/api";
import type { ExceptionType, ReconciliationSummary, Transaction } from "@/services/types";

export function Results() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [active, setActive] = useState<Transaction | null>(null);
  const [typeFilter, setTypeFilter] = useState<ExceptionType | "all">("all");
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.getResults(jobId).then(
      (s) => {
        if (alive) {
          setSummary(s);
          setLoading(false);
        }
      },
      () => {
        if (alive) {
          setSummary(null);
          setLoading(false);
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [jobId]);

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl space-y-6">
        <Skeleton className="h-8 w-72" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-72" />
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 text-center">
        <h1 className="text-[22px] font-semibold text-ink">No result set for {jobId}</h1>
        <p className="text-[13.5px] text-ink-2">
          This job could not be found, or its result set is not ready yet.
        </p>
      </div>
    );
  }

  const explained = summary.exceptions - summary.unresolved;

  const exportSummary = () => {
    window.open(api.exportUrl(summary.jobId, true), "_blank");
  };

  return (
    <div className="space-y-7">
      {/* ---------------- header ---------------- */}
      <motion.section
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
        className="flex flex-wrap items-start justify-between gap-5"
      >
        <div>
          <div className="mb-2.5 flex flex-wrap items-center gap-2">
            <Badge tone="good" icon={<CheckCircle2 className="size-3.5" />}>
              Reconciliation complete
            </Badge>
            <Badge tone="neutral" size="sm">
              {summary.jobId}
            </Badge>
            <span className="text-[12px] text-ink-3">
              {formatDateTime(summary.completedAt)} · {(summary.durationMs / 1000).toFixed(1)}s
            </span>
          </div>
          <h1 className="flex items-center gap-2.5 text-[27px] font-semibold tracking-[-0.028em] text-ink">
            Reconciliation Complete
            <PartyPopper className="size-5 text-ink-3" />
          </h1>
          <p className="mt-2 max-w-2xl text-[14.5px] leading-relaxed text-ink-2">
            Your settlement batch has been processed successfully.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <Button variant="secondary" onClick={() => navigate(`/audit?job=${summary.jobId}`)}>
            <FileClock className="size-4" />
            View audit trail
          </Button>
          <Button onClick={exportSummary}>
            <Download className="size-4" />
            Export Report
          </Button>
        </div>
      </motion.section>

      {/* ---------------- KPIs ---------------- */}
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Records Processed"
          value={summary.recordsProcessed}
          format={formatNumber}
          icon={<Layers className="size-3.5" />}
          support={<>{formatCrore(summary.grossValue)} gross value in scope</>}
        />
        <StatTile
          label="Matched"
          value={summary.matched}
          format={formatNumber}
          icon={<CheckCircle2 className="size-3.5" />}
          support="Closed by the engine with no interpretation"
          meter={{ fraction: summary.matched / summary.recordsProcessed, tone: "good" }}
        />
        <StatTile
          label="Exceptions"
          value={summary.exceptions}
          format={formatNumber}
          icon={<AlertTriangle className="size-3.5" />}
          support={
            <>
              {formatNumber(explained)} explained · {formatNumber(summary.unresolved)} unresolved
            </>
          }
          meter={{ fraction: summary.exceptions / summary.recordsProcessed, tone: "serious" }}
        />
        <StatTile
          emphasis
          label="Match Rate"
          value={summary.matchRate}
          format={(n) => formatPercent(n)}
          icon={<Target className="size-3.5" />}
          support={`${formatNumber(summary.matched)} of ${formatNumber(summary.recordsProcessed)} records · target 97.00%`}
          meter={{ fraction: summary.matchRate / 100, tone: "accent" }}
        />
      </section>

      {/* ---------------- overview + breakdown ---------------- */}
      <section className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Reconciliation Overview"
            description="Where every record in the batch ended up."
          />
          <CardBody>
            <CompositionBar
              total={summary.recordsProcessed}
              segments={[
                { key: "matched", label: "Matched", value: summary.matched, tone: "good" },
                { key: "exception", label: "Exceptions", value: explained, tone: "serious" },
                { key: "unresolved", label: "Unresolved", value: summary.unresolved, tone: "critical" },
              ]}
            />

            <div className="mt-6 grid gap-3 border-t border-line pt-5 sm:grid-cols-3">
              <MiniFigure label="Gross value" value={formatCrore(summary.grossValue)} />
              <MiniFigure label="Settled value" value={formatCrore(summary.settledValue)} />
              <MiniFigure label="Total variance" value={formatCrore(summary.varianceValue)} tone="serious" />
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Exception Breakdown"
            description="Click a category to filter the transaction table below."
            actions={
              typeFilter !== "all" ? (
                <Button variant="ghost" size="sm" onClick={() => setTypeFilter("all")}>
                  Clear filter
                </Button>
              ) : undefined
            }
          />
          <CardBody>
            <BreakdownBars
              buckets={summary.buckets}
              selected={typeFilter === "all" ? null : typeFilter}
              onSelect={(t) => setTypeFilter((cur) => (cur === t ? "all" : t))}
            />
          </CardBody>
        </Card>
      </section>

      {/* ---------------- transactions ---------------- */}
      <section className="space-y-4">
        <SectionHeader
          eyebrow="Transaction Results"
          title="Every record, searchable"
          description="Sort, filter and export the full batch. Click any row to inspect how the result was reached."
        />
        <TransactionTable
          jobId={jobId || summary.jobId}
          onOpen={setActive}
          activeOrderId={active?.orderId ?? null}
          initialType={typeFilter}
        />
      </section>

      <ExceptionDrawer jobId={jobId || summary.jobId} transaction={active} onClose={() => setActive(null)} />
    </div>
  );
}

function MiniFigure({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "serious";
}) {
  return (
    <div>
      <p className="text-[11.5px] text-ink-2">{label}</p>
      <p
        className={`tnum mt-1 text-[16px] font-semibold tracking-[-0.02em] ${
          tone === "serious" ? "text-serious-text" : "text-ink"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
