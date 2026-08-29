import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertOctagon, CheckCircle2, Clock, PlusCircle } from "lucide-react";
import { cn, formatDateTime, formatNumber, formatPercent } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Card, SectionHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/Misc";
import * as api from "@/services/api";
import type { HistoryEntry } from "@/services/types";

export function History() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<HistoryEntry[] | null>(null);

  useEffect(() => {
    let alive = true;
    api.getHistory().then((r) => {
      if (alive) setRows(r);
    });
    return () => {
      alive = false;
    };
  }, []);

  const columns = useMemo<Column<HistoryEntry>[]>(
    () => [
      {
        key: "jobId",
        header: "Job ID",
        render: (r) => <span className="tnum font-medium text-ink">{r.jobId}</span>,
      },
      {
        key: "createdAt",
        header: "Run at",
        hideBelow: "sm",
        render: (r) => <span className="text-ink-2">{formatDateTime(r.createdAt)}</span>,
      },
      {
        key: "source",
        header: "Source",
        hideBelow: "lg",
        render: (r) => <span className="text-ink-2">{r.source}</span>,
      },
      {
        key: "records",
        header: "Records",
        align: "right",
        render: (r) => <span className="tnum text-ink">{formatNumber(r.recordsProcessed)}</span>,
      },
      {
        key: "matched",
        header: "Matched",
        align: "right",
        hideBelow: "md",
        render: (r) => <span className="tnum text-ink-2">{formatNumber(r.matched)}</span>,
      },
      {
        key: "exceptions",
        header: "Exceptions",
        align: "right",
        render: (r) => <span className="tnum text-ink-2">{formatNumber(r.exceptions)}</span>,
      },
      {
        key: "matchRate",
        header: "Match rate",
        align: "right",
        render: (r) => (
          <span
            className={cn(
              "tnum font-medium",
              r.matchRate >= 97 ? "text-good-text" : r.matchRate >= 95 ? "text-ink" : "text-serious-text",
            )}
          >
            {formatPercent(r.matchRate)}
          </span>
        ),
      },
      {
        key: "duration",
        header: "Duration",
        align: "right",
        hideBelow: "xl",
        render: (r) => <span className="tnum text-ink-3">{(r.durationMs / 1000).toFixed(1)}s</span>,
      },
      {
        key: "status",
        header: "Status",
        width: "128px",
        render: (r) =>
          r.status === "completed" ? (
            <Badge tone="good" size="sm" icon={<CheckCircle2 className="size-3" />}>
              Completed
            </Badge>
          ) : (
            <Badge tone="critical" size="sm" icon={<AlertOctagon className="size-3" />}>
              Failed
            </Badge>
          ),
      },
    ],
    [],
  );

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Reconciliation history"
        title="Previous batches"
        description="Every run is retained with its full result set and audit trail. Open a batch to inspect it exactly as it was reported."
        actions={
          <Button onClick={() => navigate("/new")}>
            <PlusCircle className="size-4" />
            New Reconciliation
          </Button>
        }
      />

      <Card className="overflow-hidden">
        <DataTable
          columns={columns}
          rows={rows ?? []}
          rowKey={(r) => r.jobId}
          loading={!rows}
          skeletonRows={8}
          onRowClick={(r) => r.status === "completed" && navigate(`/results/${r.jobId}`)}
          empty={
            <EmptyState
              icon={<Clock className="size-5" />}
              title="No reconciliations yet"
              description="Run your first batch and it will appear here with its full audit trail."
              action={<Button onClick={() => navigate("/new")}>New Reconciliation</Button>}
            />
          }
        />
      </Card>

      <p className="text-center text-[11.5px] text-ink-3">
        Retention: 24 months · failed runs keep their partial audit trail for investigation
      </p>
    </div>
  );
}
