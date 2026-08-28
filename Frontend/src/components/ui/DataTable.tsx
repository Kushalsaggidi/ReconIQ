import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import { cn, formatNumber } from "@/lib/utils";
import { Skeleton } from "./Misc";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  width?: string;
  sortable?: boolean;
  /** Hide below the given breakpoint to keep narrow screens readable. */
  hideBelow?: "sm" | "md" | "lg" | "xl";
}

const HIDE = {
  sm: "hidden sm:table-cell",
  md: "hidden md:table-cell",
  lg: "hidden lg:table-cell",
  xl: "hidden xl:table-cell",
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  activeKey,
  loading,
  skeletonRows = 10,
  empty,
  sortBy,
  sortDir,
  onSort,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  activeKey?: string | null;
  loading?: boolean;
  skeletonRows?: number;
  empty?: ReactNode;
  sortBy?: string;
  sortDir?: "asc" | "desc";
  onSort?: (key: string) => void;
}) {
  const showEmpty = !loading && rows.length === 0;

  return (
    <div className="thin-scroll w-full overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-line">
            {columns.map((c) => {
              const active = sortBy === c.key;
              return (
                <th
                  key={c.key}
                  scope="col"
                  style={{ width: c.width }}
                  className={cn(
                    "sticky top-0 z-10 bg-surface-2 px-4 py-2.5 text-[11.5px] font-semibold uppercase tracking-[0.06em] text-ink-3",
                    c.align === "right" && "text-right",
                    c.hideBelow && HIDE[c.hideBelow],
                  )}
                >
                  {c.sortable && onSort ? (
                    <button
                      onClick={() => onSort(c.key)}
                      className={cn(
                        "inline-flex items-center gap-1 transition-colors hover:text-ink",
                        active && "text-ink",
                        c.align === "right" && "flex-row-reverse",
                      )}
                    >
                      {c.header}
                      {active ? (
                        sortDir === "asc" ? (
                          <ArrowUp className="size-3" strokeWidth={2.5} />
                        ) : (
                          <ArrowDown className="size-3" strokeWidth={2.5} />
                        )
                      ) : (
                        <ArrowDown className="size-3 opacity-0 transition-opacity group-hover:opacity-40" />
                      )}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading &&
            Array.from({ length: skeletonRows }).map((_, i) => (
              <tr key={`sk-${i}`} className="border-b border-line last:border-0">
                {columns.map((c) => (
                  <td key={c.key} className={cn("px-4 py-3", c.hideBelow && HIDE[c.hideBelow])}>
                    <Skeleton className={cn("h-3.5", c.align === "right" ? "ml-auto w-16" : "w-24")} />
                  </td>
                ))}
              </tr>
            ))}

          {!loading &&
            rows.map((row) => {
              const key = rowKey(row);
              const isActive = activeKey === key;
              return (
                <tr
                  key={key}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cn(
                    "group border-b border-line transition-colors duration-100 last:border-0",
                    onRowClick && "cursor-pointer",
                    isActive ? "bg-accent-soft" : "hover:bg-surface-2",
                  )}
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={cn(
                        "px-4 py-3 text-[13px] text-ink align-middle",
                        c.align === "right" && "text-right",
                        c.hideBelow && HIDE[c.hideBelow],
                      )}
                    >
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
        </tbody>
      </table>

      {showEmpty && <div className="border-t border-line">{empty}</div>}
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  totalPages,
  onPage,
  onPageSize,
}: {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPage: (p: number) => void;
  onPageSize?: (n: number) => void;
}) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line px-5 py-3">
      <p className="tnum text-[12.5px] text-ink-2">
        Showing <span className="font-medium text-ink">{formatNumber(from)}</span>–
        <span className="font-medium text-ink">{formatNumber(to)}</span> of{" "}
        <span className="font-medium text-ink">{formatNumber(total)}</span> records
      </p>

      <div className="flex items-center gap-4">
        {onPageSize && (
          <label className="flex items-center gap-2 text-[12.5px] text-ink-2">
            Rows
            <select
              value={pageSize}
              onChange={(e) => onPageSize(Number(e.target.value))}
              className="h-8 cursor-pointer rounded-md border border-line bg-surface px-2 text-[12.5px] font-medium text-ink hover:border-line-strong focus:border-accent focus:outline-none"
            >
              {[25, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        )}

        <div className="flex items-center gap-1">
          <PageBtn label="Previous page" disabled={page <= 1} onClick={() => onPage(page - 1)}>
            <ChevronLeft className="size-4" />
          </PageBtn>

          {pageWindow(page, totalPages).map((p, i) =>
            p === "…" ? (
              <span key={`gap-${i}`} className="px-1.5 text-[12.5px] text-ink-3">
                …
              </span>
            ) : (
              <button
                key={p}
                onClick={() => onPage(p)}
                className={cn(
                  "tnum h-8 min-w-8 rounded-md px-2 text-[12.5px] font-medium transition-colors duration-100",
                  p === page
                    ? "bg-accent text-accent-ink"
                    : "text-ink-2 hover:bg-surface-3 hover:text-ink",
                )}
              >
                {p}
              </button>
            ),
          )}

          <PageBtn label="Next page" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
            <ChevronRight className="size-4" />
          </PageBtn>
        </div>
      </div>
    </div>
  );
}

function PageBtn({
  children,
  disabled,
  onClick,
  label,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-8 place-items-center rounded-md text-ink-2 transition-colors duration-100 hover:bg-surface-3 hover:text-ink disabled:pointer-events-none disabled:text-ink-3/50"
    >
      {children}
    </button>
  );
}

function pageWindow(page: number, totalPages: number): (number | "…")[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const out: (number | "…")[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(totalPages - 1, page + 1);
  if (start > 2) out.push("…");
  for (let p = start; p <= end; p++) out.push(p);
  if (end < totalPages - 1) out.push("…");
  out.push(totalPages);
  return out;
}
