import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, ExternalLink, Flag, ShieldCheck } from "lucide-react";
import { formatDate, formatMoney } from "@/lib/utils";
import { Drawer } from "@/components/ui/Drawer";
import { Button } from "@/components/ui/Button";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { DetailRow, Skeleton } from "@/components/ui/Misc";
import { ExceptionWorkspace } from "./ExceptionWorkspace";
import * as api from "@/services/api";
import type { ExceptionDetail, Transaction } from "@/services/types";

/**
 * Row -> investigation. Exceptions open the full workspace; matched records get
 * a short confirmation panel, because there is nothing to investigate.
 */
export function ExceptionDrawer({
  jobId,
  transaction,
  onClose,
}: {
  jobId: string;
  transaction: Transaction | null;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<ExceptionDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!transaction || transaction.status === "matched") {
      setDetail(null);
      return;
    }
    let alive = true;
    setLoading(true);
    api.getExceptionDetail(jobId, transaction.orderId).then((d) => {
      if (alive) {
        setDetail(d);
        setLoading(false);
      }
    });
    return () => {
      alive = false;
    };
  }, [jobId, transaction]);

  const isMatched = transaction?.status === "matched";

  return (
    <Drawer
      open={Boolean(transaction)}
      onClose={onClose}
      title={transaction ? (isMatched ? `Transaction ${transaction.orderId}` : `Exception ${transaction.orderId}`) : ""}
      subtitle={
        transaction && (
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={transaction.status} size="sm" />
            <span className="text-[12px] text-ink-3">
              {transaction.status === "unresolved"
                ? "Unresolved Exception · human review required"
                : transaction.status === "exception"
                  ? `${transaction.reason}`
                  : "Reconciled with no variance"}
            </span>
          </span>
        )
      }
      footer={
        transaction && (
          <>
            <span className="text-[11.5px] text-ink-3">
              Read-only · no ledger is modified from this panel
            </span>
            <div className="flex items-center gap-2">
              {!isMatched && (
                <Link to={`/exceptions/${transaction.orderId}`} onClick={onClose}>
                  <Button variant="secondary" size="sm">
                    <ExternalLink className="size-3.5" />
                    Open full page
                  </Button>
                </Link>
              )}
              <Button size="sm" variant={transaction.status === "unresolved" ? "primary" : "secondary"}>
                <Flag className="size-3.5" />
                {transaction.status === "unresolved" ? "Assign for review" : "Mark reviewed"}
              </Button>
            </div>
          </>
        )
      }
    >
      {loading && (
        <div className="space-y-3 p-6">
          <Skeleton className="h-4 w-40" />
          <div className="grid gap-3 sm:grid-cols-3">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
          <Skeleton className="h-32" />
          <Skeleton className="h-44" />
        </div>
      )}

      {!loading && detail && <ExceptionWorkspace detail={detail} />}

      {!loading && !detail && transaction && isMatched && <MatchedPanel transaction={transaction} />}
    </Drawer>
  );
}

function MatchedPanel({ transaction: t }: { transaction: Transaction }) {
  return (
    <div className="divide-y divide-line">
      <section className="px-6 py-6">
        <div className="flex items-start gap-3 rounded-xl border border-good-line bg-good-soft px-4 py-3.5">
          <CheckCircle2 className="mt-px size-4.5 shrink-0 text-good" />
          <div>
            <p className="text-[13.5px] font-semibold text-ink">Matched with no variance</p>
            <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">
              The order amount, the settlement record and the bank credit agree to the paise. No exception was raised
              and the model was not called for this record.
            </p>
          </div>
        </div>

        <div className="mt-5 grid gap-x-8 sm:grid-cols-2">
          <div className="divide-y divide-line">
            <DetailRow label="Order ID" value={t.orderId} mono />
            <DetailRow label="Payment ID" value={t.paymentId} mono />
            <DetailRow label="Settlement ID" value={t.settlementId ?? "—"} mono />
            <DetailRow label="Bank reference" value={t.bankRef ?? "—"} mono />
          </div>
          <div className="divide-y divide-line">
            <DetailRow label="Expected amount" value={formatMoney(t.expected)} mono />
            <DetailRow label="Settled amount" value={formatMoney(t.settled)} mono />
            <DetailRow label="Difference" value={formatMoney(0)} mono tone="muted" />
            <DetailRow label="Settlement date" value={formatDate(t.settlementDate)} />
            <DetailRow label="Method" value={t.method} />
          </div>
        </div>
      </section>

      <section className="px-6 py-6">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-accent" />
          <span className="text-[12.5px] font-medium text-ink">Match keys used</span>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone="accent" size="sm">
            payment_id
          </Badge>
          <Badge tone="accent" size="sm">
            bank UTR
          </Badge>
          <Badge tone="accent" size="sm">
            amount + date window
          </Badge>
        </div>
        <p className="mt-3 text-[12px] leading-relaxed text-ink-2">
          All three keys agreed, so this record was closed by the engine without any interpretation step.
        </p>
      </section>
    </div>
  );
}
