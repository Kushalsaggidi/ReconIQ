import { useEffect, useState } from "react";
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
} from "lucide-react";
import { cn, formatCrore, formatDateTime, formatNumber, formatPercent, relativeTime } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardBody, SectionHeader } from "@/components/ui/Card";
import { StatTile } from "@/components/ui/StatTile";
import { Badge } from "@/components/ui/Badge";
import { EmptyState, Skeleton } from "@/components/ui/Misc";
import { BreakdownBars } from "@/components/charts/BreakdownBars";
import { TrendChart } from "@/components/charts/TrendChart";
import { PipelineStrip } from "@/components/recon/Pipeline";
import { useRecon } from "@/store/ReconProvider";
import { useDemoRun } from "@/lib/useDemoRun";
import * as api from "@/services/api";
import type { AuditEvent, HistoryEntry, TrendPoint } from "@/services/types";

export function Overview() {
  const { summary, refreshSummary } = useRecon();
  const navigate = useNavigate();
  const { run, starting } = useDemoRun();

  const [history, setHistory] = useState<HistoryEntry[] | null>(null);
  const [trend, setTrend] = useState<TrendPoint[] | null>(null);
  const [activity, setActivity] = useState<AuditEvent[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.getHistory().then(async (rows) => {
      if (!alive) return;
      setHistory(rows);
      const latest = rows.find((r) => r.status === "completed");
      if (latest) {
        const [, trendRows, auditRows] = await Promise.all([
          refreshSummary(latest.jobId),
          api.getTrend(latest.jobId).catch(() => []),
          api.getAuditTrail(latest.jobId).catch(() => []),
        ]);
        if (!alive) return;
        setTrend(trendRows);
        setActivity(auditRows.slice(-6).reverse());
      }
      setLoading(false);
    }, () => {
      if (alive) setLoading(false);
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="space-y-7">
        <Skeleton className="h-24" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (!summary || !history || history.length === 0) {
    return (
      <div className="space-y-7">
        <section className="max-w-2xl">
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
        </section>

        <Card>
          <EmptyState
            icon={<FileSpreadsheet className="size-5" />}
            title="Run a reconciliation to see results"
            description="Upload your orders, settlements and bank statement — or try the bundled demo batch — and this dashboard fills in with real numbers from the engine."
            action={
              <div className="flex flex-wrap items-center justify-center gap-2.5">
                <Button size="lg" onClick={() => navigate("/new")}>
                  <PlusCircle className="size-4" />
                  New Reconciliation
                </Button>
                <Button size="lg" variant="ai" onClick={run} loading={starting}>
                  {!starting && <PlayCircle className="size-4" />}
                  Try Demo Dataset
                </Button>
              </div>
            }
          />
        </Card>

        <PipelineStrip />
      </div>
    );
  }

  const prev = trend && trend.length >= 2 ? trend[trend.length - 2] : null;
  const rateDelta = prev ? summary.matchRate - prev.matchRate : 0;

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
            description="Match rate across recent batches of this job. Volumes and exception counts appear on hover."
            actions={
              <Badge tone="neutral" size="sm">
                {trend?.length ?? 0} points
              </Badge>
            }
          />
          <CardBody className="pt-5">
            {trend && trend.length > 0 ? (
              <TrendChart data={trend} />
            ) : (
              <EmptyState
                icon={<Sparkles className="size-5" />}
                title="Not enough history yet"
                description="Trend data appears once this job has recorded more than one point."
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Latest Reconciliation"
            actions={
              summary.status === "completed" ? (
                <Badge tone="good" size="sm" icon={<CheckCircle2 className="size-3" />}>
                  Completed
                </Badge>
              ) : (
                <Badge tone="critical" size="sm">
                  {summary.status}
                </Badge>
              )
            }
          />
          <CardBody className="space-y-0 py-2">
            {[
              ["Job ID", summary.jobId],
              ["Date", formatDateTime(summary.completedAt ?? summary.createdAt)],
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
            description="The last events recorded in this job's audit trail."
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
          {activity && activity.length > 0 ? (
            <ul className="divide-y divide-line">
              {activity.map((a) => {
                const isAi = a.engine === "ai";
                const isWarning = a.status === "warning";
                return (
                  <li
                    key={a.id}
                    className="flex items-start gap-3 px-6 py-3.5 transition-colors duration-100 hover:bg-surface-2"
                  >
                    <span
                      className={cn(
                        "mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg",
                        isAi ? "bg-ai-soft text-ai" : isWarning ? "bg-serious-soft text-serious-text" : "bg-surface-3 text-ink-2",
                      )}
                    >
                      {isAi ? (
                        <Sparkles className="size-3.5" strokeWidth={2.25} />
                      ) : isWarning ? (
                        <AlertTriangle className="size-3.5" strokeWidth={2.25} />
                      ) : (
                        <FileSpreadsheet className="size-3.5" strokeWidth={2.25} />
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-medium text-ink">{a.title}</p>
                      <p className="mt-0.5 truncate text-[12px] text-ink-2">{a.description}</p>
                    </div>
                    <span className="flex shrink-0 items-center gap-1 pt-0.5 text-[11.5px] text-ink-3">
                      <Clock className="size-3" />
                      {relativeTime(a.at)}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <EmptyState
              icon={<Clock className="size-5" />}
              title="No activity yet"
              description="Audit events for this job will appear here."
            />
          )}
        </Card>
      </section>

      {/* ---------------- demo nudge ---------------- */}
      <SectionHeader
        title="Ready to see it end to end?"
        description="The demo batch runs a full reconciliation — validation, deterministic matching, exception detection, AI classification and a sealed audit trail."
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
