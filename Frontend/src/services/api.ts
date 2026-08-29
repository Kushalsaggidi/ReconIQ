/**
 * Mock service layer.
 *
 * Every function here is a stand-in for one endpoint on the Python service:
 *
 *   uploadDataset      -> POST   /reconciliation/upload
 *   runReconciliation  -> POST   /reconciliation/run
 *   getJobStatus       -> GET    /reconciliation/:jobId/status
 *   getResults         -> GET    /reconciliation/:jobId/results
 *   getTransactions    -> GET    /reconciliation/:jobId/transactions
 *   getExceptions      -> GET    /reconciliation/:jobId/exceptions
 *   getExceptionDetail -> GET    /reconciliation/:jobId/exceptions/:orderId
 *   getAuditTrail      -> GET    /reconciliation/:jobId/audit
 *
 * Components never import from `dataset.ts` or `analysis.ts` — only from here —
 * so replacing the bodies below with `fetch` calls is a one-file change.
 */

import { clamp, sleep } from "@/lib/utils";
import { buildExceptionDetail } from "./analysis";
import {
  BUCKET_COUNTS,
  CAT_ORDER,
  EXCEPTION_COUNT,
  EXCEPTION_LABELS,
  EXCEPTION_TONE,
  HERO_ORDER_ID,
  MATCHED_COUNT,
  MATCH_RATE,
  TOTAL_RECORDS,
  buildTrend,
  bucketTotals,
  dayToDate,
  getExceptionIndex,
  getStore,
  getTransaction,
  indexOfOrderId,
  valueTotals,
} from "./dataset";
import type {
  ActivityItem,
  AuditEvent,
  DatasetFile,
  DatasetKind,
  ExceptionBucket,
  ExceptionDetail,
  HistoryEntry,
  JobProgress,
  ReconciliationSummary,
  StageState,
  TableQuery,
  TablePage,
  Transaction,
  TrendPoint,
  TxnStatus,
} from "./types";

export const API_BASE = "/api";
const LATENCY = 260;

/* ------------------------------------------------------------------ */
/* Demo datasets                                                       */
/* ------------------------------------------------------------------ */

export const DATASET_META: Record<
  DatasetKind,
  { title: string; description: string; accepts: string; demoFile: string; demoRows: number; demoSize: number }
> = {
  orders: {
    title: "Orders",
    description: "Merchant order and payment records",
    accepts: ".csv,.xlsx,.json",
    demoFile: "orders_2026-08-28.csv",
    demoRows: 100_000,
    demoSize: 18_411_520,
  },
  settlements: {
    title: "Settlements",
    description: "Razorpay settlement records",
    accepts: ".csv,.xlsx,.json",
    demoFile: "razorpay_settlements_2026-08-28.csv",
    demoRows: 99_730,
    demoSize: 14_286_848,
  },
  bank: {
    title: "Bank Statement",
    description: "Bank settlement / credit records",
    accepts: ".csv,.xlsx,.pdf",
    demoFile: "hdfc_statement_aug_2026.csv",
    demoRows: 4_812,
    demoSize: 2_965_504,
  },
};

export function demoDatasetFiles(): DatasetFile[] {
  const at = new Date().toISOString();
  return (Object.keys(DATASET_META) as DatasetKind[]).map((kind) => ({
    kind,
    name: DATASET_META[kind].demoFile,
    size: DATASET_META[kind].demoSize,
    rows: DATASET_META[kind].demoRows,
    status: "ready" as const,
    progress: 100,
    uploadedAt: at,
    checksum: `sha256:${kind.slice(0, 3)}9f${kind.length}c41e…`,
    isDemo: true,
  }));
}

/** POST /reconciliation/upload — streams progress back to the caller. */
export async function uploadDataset(
  kind: DatasetKind,
  file: File,
  onProgress: (p: number) => void,
): Promise<DatasetFile> {
  const steps = [8, 24, 46, 68, 87, 100];
  for (const p of steps) {
    await sleep(110 + Math.random() * 90);
    onProgress(p);
  }
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
  const allowed = DATASET_META[kind].accepts.replace(/\./g, "").split(",");
  if (!allowed.includes(ext)) {
    return {
      kind,
      name: file.name,
      size: file.size,
      rows: null,
      status: "error",
      progress: 100,
      error: `Unsupported file type “.${ext}”. Expected ${DATASET_META[kind].accepts}.`,
    };
  }
  return {
    kind,
    name: file.name,
    size: file.size,
    rows: Math.max(1, Math.round(file.size / 184)),
    status: "ready",
    progress: 100,
    uploadedAt: new Date().toISOString(),
    checksum: `sha256:${Math.abs(hash(file.name)).toString(16).padStart(8, "0")}…`,
  };
}

function hash(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return h;
}

/* ------------------------------------------------------------------ */
/* Job lifecycle                                                       */
/* ------------------------------------------------------------------ */

const STAGE_BLUEPRINT: Omit<StageState, "status">[] = [
  { id: "validate", label: "Files validated", detail: "Schema, encoding and column checks", engine: "deterministic" },
  { id: "normalize", label: "Data normalized", detail: "Currency, timezone and ID normalisation", engine: "deterministic" },
  { id: "match", label: "Transactions matched", detail: "Deterministic match on payment ID, UTR and amount", engine: "deterministic" },
  { id: "detect", label: "Detecting exceptions", detail: "Variance computed and bucketed by rule", engine: "deterministic" },
  { id: "ai", label: "AI analysis", detail: "Exception classification and explanation", engine: "ai" },
  { id: "finalize", label: "Finalizing report", detail: "Audit trail sealed and report generated", engine: "deterministic" },
];

/** Fractions of the run each stage owns. */
const STAGE_BOUNDS: [number, number][] = [
  [0, 0.06],
  [0.06, 0.16],
  [0.16, 0.62],
  [0.62, 0.78],
  [0.78, 0.94],
  [0.94, 1],
];

const RUN_MS = 11_500;

interface Job {
  jobId: string;
  startedAt: number;
  recordsDetected: number;
  source: string;
}

const jobs = new Map<string, Job>();
let sequence = 428;

export function newJobId() {
  sequence += 1;
  const d = new Date();
  const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
  return `RCN-${stamp}-${sequence}`;
}

/** POST /reconciliation/run */
export async function runReconciliation(input: {
  datasets: DatasetFile[];
  source?: string;
}): Promise<{ jobId: string; recordsDetected: number }> {
  await sleep(LATENCY);
  const jobId = newJobId();
  jobs.set(jobId, {
    jobId,
    startedAt: Date.now(),
    recordsDetected: TOTAL_RECORDS,
    source: input.source ?? "Manual upload",
  });
  return { jobId, recordsDetected: TOTAL_RECORDS };
}

/**
 * GET /reconciliation/:jobId/status
 * Pure function of elapsed time, so the client polls exactly as it will
 * against the real service.
 */
export function getJobStatus(jobId: string): JobProgress {
  const job = jobs.get(jobId) ?? {
    jobId,
    startedAt: Date.now() - RUN_MS,
    recordsDetected: TOTAL_RECORDS,
    source: "Demo dataset",
  };
  const elapsed = Date.now() - job.startedAt;
  const raw = clamp(elapsed / RUN_MS, 0, 1);
  // ease-out so the tail does not crawl
  const f = 1 - Math.pow(1 - raw, 1.85);

  const stages: StageState[] = STAGE_BLUEPRINT.map((s, i) => {
    const [from, to] = STAGE_BOUNDS[i];
    const status: StageState["status"] = f >= to ? "done" : f >= from ? "active" : "pending";
    return {
      ...s,
      status,
      startedAt: f >= from ? new Date(job.startedAt + from * RUN_MS).toISOString() : undefined,
      finishedAt: f >= to ? new Date(job.startedAt + to * RUN_MS).toISOString() : undefined,
    };
  });

  const matchFraction = clamp((f - 0.06) / (0.62 - 0.06), 0, 1);
  const recordsProcessed = Math.round(TOTAL_RECORDS * matchFraction);
  const matchedSoFar = Math.round(recordsProcessed * (MATCHED_COUNT / TOTAL_RECORDS));
  const exceptionFraction = clamp((f - 0.16) / (0.78 - 0.16), 0, 1);
  const exceptionsSoFar = Math.round(EXCEPTION_COUNT * exceptionFraction);
  const done = raw >= 1;
  const active = stages.find((s) => s.status === "active");

  return {
    jobId,
    status: done ? "completed" : "running",
    recordsDetected: job.recordsDetected,
    recordsProcessed: done ? TOTAL_RECORDS : recordsProcessed,
    matchedSoFar: done ? MATCHED_COUNT : matchedSoFar,
    exceptionsSoFar: done ? EXCEPTION_COUNT : exceptionsSoFar,
    ratePerSecond: elapsed > 400 ? Math.round(recordsProcessed / (elapsed / 1000)) : 0,
    elapsedMs: elapsed,
    etaMs: Math.max(0, RUN_MS - elapsed),
    percent: f * 100,
    stages,
    currentStageLabel: done ? "Completed" : active?.label ?? "Queued",
  };
}

/* ------------------------------------------------------------------ */
/* Results                                                            */
/* ------------------------------------------------------------------ */

function buckets(): ExceptionBucket[] {
  const amounts = bucketTotals();
  return CAT_ORDER.map((type) => ({
    type,
    label: EXCEPTION_LABELS[type],
    count: BUCKET_COUNTS[type],
    amount: amounts[type],
    autoExplained: EXCEPTION_TONE[type] === "explained",
  }));
}

/** GET /reconciliation/:jobId/results */
export async function getResults(jobId: string, datasets?: DatasetFile[]): Promise<ReconciliationSummary> {
  await sleep(LATENCY);
  return getResultsSync(jobId, datasets);
}

export function getResultsSync(jobId: string, datasets?: DatasetFile[]): ReconciliationSummary {
  const job = jobs.get(jobId);
  const completedAt = job ? new Date(job.startedAt + RUN_MS) : new Date();
  const totals = valueTotals();
  const ds = (datasets?.length ? datasets : demoDatasetFiles()).map((d) => ({
    kind: d.kind,
    name: d.name,
    rows: d.rows ?? 0,
  }));
  return {
    jobId,
    createdAt: new Date(completedAt.getTime() - RUN_MS).toISOString(),
    completedAt: completedAt.toISOString(),
    durationMs: RUN_MS,
    status: "completed",
    recordsProcessed: TOTAL_RECORDS,
    matched: MATCHED_COUNT,
    exceptions: EXCEPTION_COUNT,
    unresolved: BUCKET_COUNTS.unresolved,
    matchRate: MATCH_RATE,
    grossValue: totals.gross,
    settledValue: totals.settled,
    varianceValue: totals.variance,
    buckets: buckets(),
    datasets: ds,
  };
}

export async function getTrend(): Promise<TrendPoint[]> {
  await sleep(120);
  return buildTrend();
}

export function getTrendSync(): TrendPoint[] {
  return buildTrend();
}

/* ------------------------------------------------------------------ */
/* Transaction table — server-shaped pagination                        */
/* ------------------------------------------------------------------ */

const filterCache = new Map<string, Int32Array>();

function buildFilteredIndex(q: TableQuery, exceptionsOnly: boolean): Int32Array {
  const key = JSON.stringify([
    q.status ?? "all",
    q.exceptionType ?? "all",
    q.dateRange ?? "all",
    (q.search ?? "").trim().toLowerCase(),
    exceptionsOnly,
    q.sortBy ?? "orderId",
    q.sortDir ?? "asc",
  ]);
  const hit = filterCache.get(key);
  if (hit) return hit;

  const s = getStore();
  const search = (q.search ?? "").trim().toLowerCase();
  const wantStatus = q.status ?? "all";
  const wantType = q.exceptionType ?? "all";
  const days = q.dateRange === "7d" ? 7 : q.dateRange === "14d" ? 14 : q.dateRange === "30d" ? 30 : 0;
  const minDay = days ? 14 - Math.min(14, days) : 0;

  // A direct order-ID search collapses to a single index lookup.
  const direct = search ? indexOfOrderId(search) : null;

  const source: Int32Array | null = exceptionsOnly ? getExceptionIndex() : null;
  const len = source ? source.length : TOTAL_RECORDS;
  const out: number[] = [];

  for (let k = 0; k < len; k++) {
    const i = source ? source[k] : k;
    const cat = s.cat[i];
    const type = cat === 0 ? null : CAT_ORDER[cat - 1];
    const status: TxnStatus = cat === 0 ? "matched" : type === "unresolved" ? "unresolved" : "exception";

    if (wantStatus !== "all" && status !== wantStatus) continue;
    if (wantType !== "all" && type !== wantType) continue;
    if (days && s.day[i] < minDay) continue;
    if (search) {
      if (direct !== null) {
        if (i !== direct) continue;
      } else {
        const t = getTransaction(i);
        const hay = `${t.orderId} ${t.paymentId} ${t.settlementId ?? ""} ${t.bankRef ?? ""} ${t.reason}`.toLowerCase();
        if (!hay.includes(search)) continue;
      }
    }
    out.push(i);
  }

  const arr = Int32Array.from(out);
  sortIndex(arr, q.sortBy ?? "orderId", q.sortDir ?? "asc");
  if (filterCache.size > 24) filterCache.clear();
  filterCache.set(key, arr);
  return arr;
}

function sortIndex(arr: Int32Array, by: NonNullable<TableQuery["sortBy"]>, dir: "asc" | "desc") {
  const s = getStore();
  const sign = dir === "asc" ? 1 : -1;
  const value = (i: number) => {
    switch (by) {
      case "expected":
        return s.expected[i];
      case "settled":
        return s.expected[i] - s.difference[i];
      case "difference":
        return s.difference[i];
      case "settlementDate":
        return s.day[i] * 100_000 + i;
      default:
        return i;
    }
  };
  const sorted = Array.from(arr).sort((a, b) => sign * (value(a) - value(b)));
  arr.set(sorted);
}

function facetsFor(q: TableQuery, exceptionsOnly: boolean) {
  // Facet counts ignore the status filter so the chips can show what's behind them.
  const base = buildFilteredIndex({ ...q, status: "all", page: 1, pageSize: 1 }, exceptionsOnly);
  const s = getStore();
  let matched = 0;
  let exception = 0;
  let unresolved = 0;
  for (let k = 0; k < base.length; k++) {
    const cat = s.cat[base[k]];
    if (cat === 0) matched++;
    else if (cat === 5) unresolved++;
    else exception++;
  }
  return { matched, exception, unresolved };
}

/** GET /reconciliation/:jobId/transactions */
export async function getTransactions(_jobId: string, q: TableQuery): Promise<TablePage> {
  await sleep(140);
  return pageOf(q, false);
}

/** GET /reconciliation/:jobId/exceptions */
export async function getExceptions(_jobId: string, q: TableQuery): Promise<TablePage> {
  await sleep(140);
  return pageOf(q, true);
}

function pageOf(q: TableQuery, exceptionsOnly: boolean): TablePage {
  const idx = buildFilteredIndex(q, exceptionsOnly);
  const pageSize = q.pageSize;
  const totalPages = Math.max(1, Math.ceil(idx.length / pageSize));
  const page = clamp(q.page, 1, totalPages);
  const start = (page - 1) * pageSize;
  const rows: Transaction[] = [];
  for (let k = start; k < Math.min(start + pageSize, idx.length); k++) {
    rows.push(getTransaction(idx[k]));
  }
  return {
    rows,
    total: idx.length,
    page,
    pageSize,
    totalPages,
    facets: facetsFor(q, exceptionsOnly),
  };
}

/** GET /reconciliation/:jobId/exceptions/:orderId */
export async function getExceptionDetail(_jobId: string, orderId: string): Promise<ExceptionDetail | null> {
  await sleep(200);
  return buildExceptionDetail(orderId);
}

export function getExceptionDetailSync(orderId: string): ExceptionDetail | null {
  return buildExceptionDetail(orderId);
}

/* ------------------------------------------------------------------ */
/* Audit trail                                                        */
/* ------------------------------------------------------------------ */

/** GET /reconciliation/:jobId/audit */
export async function getAuditTrail(jobId: string): Promise<AuditEvent[]> {
  await sleep(160);
  return getAuditTrailSync(jobId);
}

export function getAuditTrailSync(jobId: string): AuditEvent[] {
  const job = jobs.get(jobId);
  const t0 = job ? job.startedAt : Date.now() - RUN_MS;
  const at = (ms: number) => new Date(t0 + ms).toISOString();

  const spec: [number, string, string, AuditEvent["actor"], AuditEvent["engine"], AuditEvent["status"], Record<string, string>?][] = [
    [0, "Reconciliation job created", `Job ${jobId} queued by kushal.saggidi@realpage.com`, "User", "system", "info", { source: job?.source ?? "Demo dataset" }],
    [700, "Orders dataset loaded", "100,000 rows parsed · schema v2 · 0 rejected", "Engine", "deterministic", "ok", { file: DATASET_META.orders.demoFile }],
    [1_200, "Settlement dataset loaded", "99,730 rows parsed · schema v2 · 0 rejected", "Engine", "deterministic", "ok", { file: DATASET_META.settlements.demoFile }],
    [1_700, "Bank statement loaded", "4,812 credit lines parsed · 0 rejected", "Engine", "deterministic", "ok", { file: DATASET_META.bank.demoFile }],
    [2_100, "100,000 records identified", "Currency normalised to INR · timestamps normalised to IST", "Engine", "deterministic", "ok"],
    [2_600, "Deterministic matching started", "Match keys: payment ID → UTR → amount + date window", "Engine", "deterministic", "info"],
    [7_100, "97,240 records reconciled", "Exact match on amount, settlement ID and bank UTR", "Engine", "deterministic", "ok", { matchRate: "97.24%" }],
    [8_900, "2,760 exceptions detected", "Variance computed per record and bucketed by rule", "Engine", "deterministic", "warning"],
    [9_100, "Exception analysis started", "2,490 exceptions routed to the classifier; 270 held back", "AI Analyst", "ai", "info", { model: "claude-sonnet-4.5" }],
    [10_800, "Exception analysis completed", "2,490 classified with explanation · 270 returned as unresolved", "AI Analyst", "ai", "ok", { avgConfidence: "High" }],
    [11_100, "270 exceptions flagged for human review", "No supporting record explains the variance — no value was inferred", "Engine", "deterministic", "warning"],
    [11_400, "Report generated", "Immutable result set sealed · checksum recorded", "System", "system", "ok", { checksum: "sha256:9c41e…" }],
  ];

  return spec.map(([ms, title, description, actor, engine, status, meta], i) => ({
    id: `${jobId}-ev-${i}`,
    at: at(ms),
    title,
    description,
    actor,
    engine,
    status,
    meta,
  }));
}

/* ------------------------------------------------------------------ */
/* History + activity                                                 */
/* ------------------------------------------------------------------ */

export function getHistorySync(latest?: ReconciliationSummary): HistoryEntry[] {
  const rows: HistoryEntry[] = [];
  const trend = buildTrend();
  for (let i = trend.length - 2; i >= 0; i--) {
    const p = trend[i];
    rows.push({
      jobId: `RCN-${new Date(p.date).toISOString().slice(0, 10).replace(/-/g, "")}-${400 + i}`,
      createdAt: p.date,
      recordsProcessed: p.processed,
      matched: p.matched,
      exceptions: p.exceptions,
      matchRate: p.matchRate,
      status: i === 6 ? "failed" : "completed",
      durationMs: 8_400 + i * 420,
      source: i % 3 === 0 ? "Scheduled · 02:00 IST" : "Manual upload",
    });
  }
  if (latest) {
    rows.unshift({
      jobId: latest.jobId,
      createdAt: latest.createdAt,
      recordsProcessed: latest.recordsProcessed,
      matched: latest.matched,
      exceptions: latest.exceptions,
      matchRate: latest.matchRate,
      status: latest.status,
      durationMs: latest.durationMs,
      source: "Demo dataset",
    });
  }
  return rows;
}

export async function getHistory(latest?: ReconciliationSummary): Promise<HistoryEntry[]> {
  await sleep(140);
  return getHistorySync(latest);
}

export function getActivitySync(): ActivityItem[] {
  const now = Date.now();
  const mins = (m: number) => new Date(now - m * 60_000).toISOString();
  return [
    { id: "a1", at: mins(4), title: "Report generated", detail: "RCN-20260828-428 · 100,000 records · 97.24% match rate", kind: "job" },
    { id: "a2", at: mins(5), title: "270 exceptions flagged for review", detail: "Held back by the engine — no value inferred", kind: "exception" },
    { id: "a3", at: mins(5), title: "AI classified 2,490 exceptions", detail: "Avg confidence High · 1,020 partial payment, 640 refund", kind: "ai" },
    { id: "a4", at: mins(9), title: "Bank statement uploaded", detail: "hdfc_statement_aug_2026.csv · 4,812 credit lines", kind: "upload" },
    { id: "a5", at: mins(64), title: "Exception O-10482 assigned", detail: "Assigned to treasury.ops for manual review", kind: "user" },
    { id: "a6", at: mins(1_450), title: "Report generated", detail: "RCN-20260827-427 · 88,412 records · 96.81% match rate", kind: "job" },
  ];
}

/* ------------------------------------------------------------------ */
/* Export                                                             */
/* ------------------------------------------------------------------ */

/** Builds a CSV client-side; the real service will stream this from Python. */
export function buildExportCsv(q: TableQuery, exceptionsOnly: boolean, limit = 5_000): string {
  const idx = buildFilteredIndex(q, exceptionsOnly);
  const head = [
    "order_id",
    "payment_id",
    "settlement_id",
    "bank_reference",
    "expected_amount",
    "settled_amount",
    "difference",
    "status",
    "exception_type",
    "reason",
    "settlement_date",
  ].join(",");
  const lines = [head];
  const n = Math.min(idx.length, limit);
  for (let k = 0; k < n; k++) {
    const t = getTransaction(idx[k]);
    lines.push(
      [
        t.orderId,
        t.paymentId,
        t.settlementId ?? "",
        t.bankRef ?? "",
        (t.expected / 100).toFixed(2),
        (t.settled / 100).toFixed(2),
        (t.difference / 100).toFixed(2),
        t.status,
        t.exceptionType ?? "",
        `"${t.reason}"`,
        t.settlementDate.slice(0, 10),
      ].join(","),
    );
  }
  return lines.join("\n");
}

export {
  EXCEPTION_LABELS,
  EXCEPTION_COUNT,
  MATCHED_COUNT,
  HERO_ORDER_ID,
  TOTAL_RECORDS,
  MATCH_RATE,
  dayToDate,
};
