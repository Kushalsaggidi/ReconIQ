import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Filter, SearchX } from "lucide-react";
import { cn, formatMoney, formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { DataTable, Pagination, type Column } from "@/components/ui/DataTable";
import { SearchInput, Segmented, Select } from "@/components/ui/Field";
import { EmptyState } from "@/components/ui/Misc";
import { ExceptionTypeBadge, StatusBadge } from "@/components/ui/Badge";
import * as api from "@/services/api";

import type { ExceptionType, TableQuery, TablePage, Transaction, TxnStatus } from "@/services/types";

const STATUS_OPTIONS: { value: TxnStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "matched", label: "Matched" },
  { value: "exception", label: "Exception" },
  { value: "unresolved", label: "Unresolved" },
];

const TYPE_OPTIONS: { value: ExceptionType | "all"; label: string }[] = [
  { value: "all", label: "All types" },
  ...(Object.keys(api.EXCEPTION_LABELS) as ExceptionType[]).map((t) => ({
    value: t,
    label: api.EXCEPTION_LABELS[t],
  })),
];

const DATE_OPTIONS = [
  { value: "all", label: "Full batch window" },
  { value: "7d", label: "Last 7 days" },
  { value: "14d", label: "Last 14 days" },
  { value: "30d", label: "Last 30 days" },
] as const;

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function TransactionTable({
  jobId,
  exceptionsOnly = false,
  onOpen,
  activeOrderId,
  initialSearch = "",
  initialType = "all",
  initialStatus = "all",
  compact,
}: {
  jobId: string;
  exceptionsOnly?: boolean;
  onOpen: (t: Transaction) => void;
  activeOrderId?: string | null;
  initialSearch?: string;
  initialType?: ExceptionType | "all";
  initialStatus?: TxnStatus | "all";
  compact?: boolean;
}) {
  const [search, setSearch] = useState(initialSearch);
  const debounced = useDebounced(search, 220);
  const [status, setStatus] = useState<TxnStatus | "all">(initialStatus);
  const [type, setType] = useState<ExceptionType | "all">(initialType);
  const [dateRange, setDateRange] = useState<TableQuery["dateRange"]>("all");
  const [sortBy, setSortBy] = useState<NonNullable<TableQuery["sortBy"]>>("orderId");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [data, setData] = useState<TablePage | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => setType(initialType), [initialType]);
  useEffect(() => setSearch(initialSearch), [initialSearch]);

  const query = useMemo<TableQuery>(
    () => ({ page, pageSize, search: debounced, status, exceptionType: type, dateRange, sortBy, sortDir }),
    [page, pageSize, debounced, status, type, dateRange, sortBy, sortDir],
  );

  // reset to the first page whenever the result set changes shape
  useEffect(() => setPage(1), [debounced, status, type, dateRange, pageSize]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const fetcher = exceptionsOnly ? api.getExceptions : api.getTransactions;
    fetcher(jobId, query).then((res) => {
      if (alive) {
        setData(res);
        setLoading(false);
      }
    });
    return () => {
      alive = false;
    };
  }, [jobId, query, exceptionsOnly]);

  const onSort = useCallback(
    (key: string) => {
      const k = key as NonNullable<TableQuery["sortBy"]>;
      if (k === sortBy) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      else {
        setSortBy(k);
        setSortDir(k === "orderId" ? "asc" : "desc");
      }
    },
    [sortBy],
  );

  const exportCsv = () => {
    window.open(api.exportUrl(jobId, exceptionsOnly), "_blank");
  };

  const columns: Column<Transaction>[] = [
    {
      key: "orderId",
      header: "Order ID",
      sortable: true,
      width: "120px",
      render: (t) => <span className="tnum font-medium text-ink">{t.orderId}</span>,
    },
    {
      key: "paymentId",
      header: "Payment ID",
      hideBelow: "lg",
      render: (t) => <span className="tnum text-ink-2">{t.paymentId}</span>,
    },
    {
      key: "settlementId",
      header: "Settlement ID",
      hideBelow: "xl",
      render: (t) =>
        t.settlementId ? (
          <span className="tnum text-ink-2">{t.settlementId}</span>
        ) : (
          <span className="text-[12px] italic text-critical-text">not found</span>
        ),
    },
    {
      key: "expected",
      header: "Expected",
      align: "right",
      sortable: true,
      render: (t) => <span className="tnum text-ink">{formatMoney(t.expected)}</span>,
    },
    {
      key: "settled",
      header: "Settled",
      align: "right",
      sortable: true,
      render: (t) => <span className="tnum text-ink">{formatMoney(t.settled)}</span>,
    },
    {
      key: "difference",
      header: "Difference",
      align: "right",
      sortable: true,
      render: (t) => (
        <span
          className={cn(
            "tnum font-medium",
            t.difference === 0 ? "text-ink-3" : t.status === "unresolved" ? "text-critical-text" : "text-ink",
          )}
        >
          {t.difference === 0 ? "—" : formatMoney(-t.difference, { signed: true })}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      width: "132px",
      render: (t) => <StatusBadge status={t.status} size="sm" />,
    },
    {
      key: "reason",
      header: "Reason",
      hideBelow: "md",
      render: (t) => (
        <div className="flex min-w-0 items-center gap-2">
          <ExceptionTypeBadge type={t.exceptionType} />
          <span className="truncate text-[12.5px] text-ink-2" title={t.reason}>
            {t.reason}
          </span>
        </div>
      ),
    },
  ];

  const facets = data?.facets;

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface shadow-xs">
      {/* filter row — one row above the table, as the interaction spec wants */}
      <div className="flex flex-col gap-3 border-b border-line bg-surface-2 px-5 py-3.5 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Order, payment, settlement or UTR"
            className="w-full sm:max-w-[268px]"
          />
          {!exceptionsOnly && (
            <Segmented
              value={status}
              onChange={setStatus}
              options={STATUS_OPTIONS.map((o) => ({
                value: o.value,
                label: o.label,
                count:
                  !facets || o.value === "all"
                    ? undefined
                    : o.value === "matched"
                      ? facets.matched
                      : o.value === "exception"
                        ? facets.exception
                        : facets.unresolved,
              }))}
            />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Select
            label="Type"
            value={type}
            onChange={(e) => setType(e.target.value as ExceptionType | "all")}
            className="w-[186px]"
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <Select
            label="Dates"
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value as TableQuery["dateRange"])}
            className="w-[212px]"
          >
            {DATE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <Button variant="secondary" size="md" onClick={exportCsv}>
            <Download className="size-4" />
            Export Report
          </Button>
        </div>
      </div>

      <DataTable
        columns={columns}
        rows={data?.rows ?? []}
        rowKey={(t) => t.orderId}
        onRowClick={onOpen}
        activeKey={activeOrderId}
        loading={loading && !data}
        skeletonRows={compact ? 6 : 10}
        sortBy={sortBy}
        sortDir={sortDir}
        onSort={onSort}
        empty={
          <EmptyState
            icon={<SearchX className="size-5" />}
            title="No records match these filters"
            description="Adjust the search term, status or date range to widen the result set."
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setSearch("");
                  setStatus("all");
                  setType("all");
                  setDateRange("all");
                }}
              >
                <Filter className="size-3.5" />
                Clear all filters
              </Button>
            }
          />
        }
      />

      {data && data.total > 0 && (
        <Pagination
          page={data.page}
          pageSize={data.pageSize}
          total={data.total}
          totalPages={data.totalPages}
          onPage={setPage}
          onPageSize={setPageSize}
        />
      )}

      <div className="flex items-center justify-between gap-3 border-t border-line bg-surface-2 px-5 py-2.5">
        <p className="text-[11.5px] text-ink-3">
          Rows are paged server-side — the full batch of {formatNumber(data?.total ?? 0)} records is never rendered
          at once.
        </p>
        {loading && data && <span className="text-[11.5px] text-ink-3">Updating…</span>}
      </div>
    </div>
  );
}
