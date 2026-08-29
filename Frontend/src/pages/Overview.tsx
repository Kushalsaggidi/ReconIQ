import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Cpu,
  FileSpreadsheet,
  Layers,
  PlayCircle,
  PlusCircle,
  Sparkles,
  Target,
  User,
} from "lucide-react";
import { cn, formatCrore, formatDateTime, formatNumber, formatPercent, relativeTime } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardBody, SectionHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { Badge } from "@/components/ui/Badge";
import { BreakdownBars } from "@/components/charts/BreakdownBars";
import { TrendChart } from "@/components/charts/TrendChart";
import { PipelineStrip } from "@/components/recon/Pipeline";
import { useRecon } from "@/store/ReconProvider";
import { useDemoRun } from "@/lib/useDemoRun";
import * as api from "@/services/api";

const ACTIVITY_ICON = {
  job: FileSpreadsheet,
  exception: AlertTriangle,
  ai: Sparkles,
  upload: Layers,
  user: User,
};

export function Overview() {
  const { ensureSummary } = useRecon();
  const navigate = useNavigate();
  const { run, starting } = useDemoRun();

  const summary = useMemo(() => ensureSummary(), [ensureSummary]);
  const trend = useMemo(() => api.getTrendSync(), []);
  const activity = useMemo(() => api.getActivitySync(), []);

  const prev = trend[trend.length - 2];
  const rateDelta = summary.matchRate - prev.matchRate;

  return (
    <div className="space-y-7">
      {/* ---------------- hero ---------------- */}
      <section className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
        <div className="max-w-2xl">
          <div className="mb-3 flex items-center gap-2">
            <Badge tone="accent" size="sm" icon={<Cpu className="size-3" />}>
              Reconciliation engine v4.2
            </Badge>
            <Badge tone="ai" size="sm" icon={<Sparkles className="size-3" />}>
              AI-assisted exception analysis
            </Badge>
          </div>
          <h1 className="text-[30px] font-semibold leading-[1.15] tracking-[-0.03em] text-ink sm:text-[34px]">
            Settlement Reconciliation
          </h1>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-2">
            Reconcile payment settlements, identify exceptions, and understand every discrepancy.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <Button size="lg" onClick={() => navigate("/new")}>
            <PlusCircle className="size-4" />
            New Reconciliation
          </Button>
          <Button size="lg" variant="secondary" onClick={() => navigate("/history")}>
            View History
          </Button>
          <Button size="lg" variant="ai" onClick={run} loading={starting}>
            {!starting && <PlayCircle className="size-4" />}
            Try Demo Dataset
          </Button>
        </div>
      </section>

      {/* ---------------- KPIs ---------------- */}
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Total Transactions"
          value={summary.recordsProcessed}
          format={formatNumber}
          icon={<Layers className="size-3.5" />}
          support={<>Across {summary.datasets.length} datasets · {formatCrore(summary.grossValue)} gross</>}
        />
        <StatTile
          label="Matched"
          value={summary.matched}
          format={formatNumber}
          icon={<CheckCircle2 className="size-3.5" />}
          support="Exact match on amount, settlement ID and UTR"
          meter={{ fraction: summary.matched / summary.recordsProcessed, tone: "good" }}
        />
        <StatTile
          label="Exceptions"
          value={summary.exceptions}
          format={formatNumber}
          icon={<AlertTriangle className="size-3.5" />}
          support={<>{formatNumber(summary.unresolved)} unresolved · {formatCrore(summary.varianceValue)} variance</>}
          meter={{ fraction: summary.exceptions / summary.recordsProcessed, tone: "serious" }}
        />
        <StatTile
          emphasis
          label="Match Rate"
          value={summary.matchRate}
          format={(n) => formatPercent(n)}
          icon={<Target className="size-3.5" />}
          delta={{
            value: rateDelta,
            label: `${rateDelta >= 0 ? "+" : ""}${rateDelta.toFixed(2)} pts`,
            direction: rateDelta > 0 ? "up" : rateDelta < 0 ? "down" : "flat",
            good: rateDelta >= 0,
          }}
          support="Versus the previous batch · target 97.00%"
        />
      </section>

      <PipelineStrip />

      {/* ---------------- trend + latest ---------------- */}
      <section className="grid gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Reconciliation performance"
            description="Match rate across the last 14 batches. Volumes and exception counts appear on hover."
            actions={
              <Badge tone="neutral" size="sm">
                Last 14 batches
              </Badge>
            }
          />
          <CardBody className="pt-5">
            <TrendChart data={trend} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Latest Reconciliation"
            actions={
              <Badge tone="good" size="sm" icon={<CheckCircle2 className="size-3" />}>
                Completed
              </Badge>
            }
          />
          <CardBody className="space-y-0 py-2">
            {[
              ["Job ID", summary.jobId],
              ["Date", formatDateTime(summary.completedAt)],
              ["Transactions processed", formatNumber(summary.recordsProcessed)],
              ["Match rate", formatPercent(summary.matchRate)],
              ["Exceptions", formatNumber(summary.exceptions)],
              ["Unresolved", formatNumber(summary.unresolved)],
              ["Duration", `${(summary.durationMs / 1000).toFixed(1)}s`],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 last:border-0"
              >
                <span className="text-[12.5px] text-ink-2">{label}</span>
                <span className="tnum text-[13px] font-medium text-ink">{value}</span>
              </div>
            ))}
          </CardBody>
          <div className="border-t border-line p-4">
            <Button
              variant="secondary"
              className="w-full"
              onClick={() => navigate(`/results/${summary.jobId}`)}
            >
              Open results
              <ArrowRight className="size-4" />
            </Button>
          </div>
        </Card>
      </section>

      {/* ---------------- breakdown + activity ---------------- */}
      <section className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Exception Breakdown"
            description={`${formatNumber(summary.exceptions)} exceptions across 5 categories. ${formatNumber(summary.unresolved)} could not be explained by any record.`}
            actions={
              <Link
                to="/exceptions"
                className="inline-flex items-center gap-1 text-[12.5px] font-medium text-accent-text hover:underline"
              >
                All exceptions
                <ArrowUpRight className="size-3.5" />
              </Link>
            }
          />
          <CardBody>
            <BreakdownBars
              buckets={summary.buckets}
              onSelect={(type) => navigate(`/exceptions?type=${type}`)}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Recent Activity"
            description="Everything the engine, the model and your team have done."
            actions={
              <Link
                to="/audit"
                className="inline-flex items-center gap-1 text-[12.5px] font-medium text-accent-text hover:underline"
              >
                Audit logs
                <ArrowUpRight className="size-3.5" />
              </Link>
            }
          />
          <ul className="divide-y divide-line">
            {activity.map((a) => {
              const Icon = ACTIVITY_ICON[a.kind];
              return (
                <li
                  key={a.id}
                  className="flex items-start gap-3 px-6 py-3.5 transition-colors duration-100 hover:bg-surface-2"
                >
                  <span
                    className={cn(
                      "mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg",
                      a.kind === "ai"
                        ? "bg-ai-soft text-ai"
                        : a.kind === "exception"
                          ? "bg-serious-soft text-serious-text"
                          : "bg-surface-3 text-ink-2",
                    )}
                  >
                    <Icon className="size-3.5" strokeWidth={2.25} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-ink">{a.title}</p>
                    <p className="mt-0.5 truncate text-[12px] text-ink-2">{a.detail}</p>
                  </div>
                  <span className="flex shrink-0 items-center gap-1 pt-0.5 text-[11.5px] text-ink-3">
                    <Clock className="size-3" />
                    {relativeTime(a.at)}
                  </span>
                </li>
              );
            })}
          </ul>
        </Card>
      </section>

      {/* ---------------- demo nudge ---------------- */}
      <SectionHeader
        title="Ready to see it end to end?"
        description="The demo batch runs a full 100,000-record reconciliation — validation, deterministic matching, exception detection, AI classification and a sealed audit trail."
        actions={
          <Button onClick={run} loading={starting}>
            {!starting && <PlayCircle className="size-4" />}
            Try Demo Dataset
          </Button>
        }
        className="rounded-xl border border-line bg-surface px-6 py-5 shadow-xs"
      />
    </div>
  );
}
