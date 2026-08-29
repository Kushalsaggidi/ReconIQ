import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Flag, SearchX, Share2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { StatusBadge, Badge } from "@/components/ui/Badge";
import { EmptyState, Skeleton } from "@/components/ui/Misc";
import { ExceptionWorkspace } from "@/components/recon/ExceptionWorkspace";
import { exceptionTypeLabel } from "@/services/analysis";
import * as api from "@/services/api";
import { useRecon } from "@/store/ReconProvider";
import { formatDate } from "@/lib/utils";
import type { ExceptionDetail } from "@/services/types";

export function ExceptionDetailPage() {
  const { orderId = "" } = useParams();
  const navigate = useNavigate();
  const { ensureSummary } = useRecon();
  const summary = useMemo(() => ensureSummary(), [ensureSummary]);
  const [detail, setDetail] = useState<ExceptionDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api.getExceptionDetail(summary.jobId, orderId).then((d) => {
      if (alive) {
        setDetail(d);
        setLoading(false);
      }
    });
    return () => {
      alive = false;
    };
  }, [orderId, summary.jobId]);

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        <Skeleton className="h-6 w-56" />
        <Card>
          <div className="space-y-4 p-6">
            <div className="grid gap-3 sm:grid-cols-3">
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
              <Skeleton className="h-24" />
            </div>
            <Skeleton className="h-40" />
            <Skeleton className="h-52" />
          </div>
        </Card>
      </div>
    );
  }

  if (!detail) {
    return (
      <Card className="mx-auto max-w-2xl">
        <EmptyState
          icon={<SearchX className="size-5" />}
          title={`No exception found for ${orderId}`}
          description="Either the order ID does not exist in this batch, or the record reconciled cleanly and has no exception to investigate."
          action={
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => navigate("/exceptions")}>
                Back to exceptions
              </Button>
              <Button onClick={() => navigate(`/exceptions/${api.HERO_ORDER_ID}`)}>
                Open a live example
              </Button>
            </div>
          }
        />
      </Card>
    );
  }

  const t = detail.transaction;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link
        to="/exceptions"
        className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-ink-2 transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-3.5" />
        All exceptions
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-semibold tracking-[-0.028em] text-ink">Exception {t.orderId}</h1>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <StatusBadge status={t.status} />
            <Badge tone="neutral" size="sm">
              {exceptionTypeLabel(t)}
            </Badge>
            <span className="text-[12.5px] text-ink-2">
              {t.status === "unresolved" ? "Unresolved Exception" : t.reason} · settled {formatDate(t.settlementDate)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm">
            <Share2 className="size-3.5" />
            Share case
          </Button>
          <Button size="sm">
            <Flag className="size-3.5" />
            {t.status === "unresolved" ? "Assign for review" : "Mark reviewed"}
          </Button>
        </div>
      </div>

      <Card>
        <ExceptionWorkspace detail={detail} />
      </Card>

      <p className="text-center text-[11.5px] text-ink-3">
        Case {t.orderId} · batch {summary.jobId} · every step is recorded in the audit trail
      </p>
    </div>
  );
}
