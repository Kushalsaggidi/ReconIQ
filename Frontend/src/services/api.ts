/**
 * Real service layer — talks to the FastAPI reconciliation backend.
 *
 *   uploadDataset      -> POST   /reconciliation/upload
 *   runReconciliation  -> POST   /reconciliation/run
 *   getJobStatus       -> GET    /reconciliation/:jobId/status
 *   getResults         -> GET    /reconciliation/:jobId/results
 *   getTrend           -> GET    /reconciliation/:jobId/trend
 *   getTransactions    -> GET    /reconciliation/:jobId/transactions
 *   getExceptions      -> GET    /reconciliation/:jobId/exceptions
 *   getExceptionDetail -> GET    /reconciliation/:jobId/exceptions/:orderId
 *   getAuditTrail      -> GET    /reconciliation/:jobId/audit
 *   getHistory         -> GET    /reconciliation/jobs
 *
 * Components never build fetch calls themselves — only from here.
 */

import type {
  AuditEvent,
  AuditPage,
  DatasetFile,
  DatasetKind,
  ExceptionDetail,
  HistoryEntry,
  JobProgress,
  ReconciliationSummary,
  TableQuery,
  TablePage,
  Transaction,
  TrendPoint,
} from "./types";

export const API_BASE = "/api/reconciliation";

export const EXCEPTION_LABELS: Record<string, string> = {
  partial_payment: "Partial payment",
  refund: "Refund",
  fee_tax: "Fee / tax",
  rounding: "Rounding",
  unresolved: "Unresolved",
};

/* ------------------------------------------------------------------ */
/* Fetch helpers                                                       */
/* ------------------------------------------------------------------ */

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    let code: string | undefined;
    try {
      const body = await res.json();
      message = body?.error?.message ?? message;
      code = body?.error?.code;
    } catch {
      // non-JSON error body — keep the generic message
    }
    throw new ApiError(message, res.status, code);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

/* ------------------------------------------------------------------ */
/* Datasets                                                            */
/* ------------------------------------------------------------------ */

/**
 * Fallback formats/limit used before `/health` has answered, or if it fails.
 * These mirror the backend's own defaults (see `Settings` in
 * `app/core/config.py`) but `/health` is the actual single source of truth —
 * fetched once and cached by `getUploadConfig`.
 */
const FALLBACK_UPLOAD_CONFIG: UploadConfig = {
  allowedFormats: ["csv", "xlsx", "xls", "json"],
  maxBytes: 512 * 1024 * 1024,
};

export interface UploadConfig {
  allowedFormats: string[];
  maxBytes: number;
}

let uploadConfigCache: Promise<UploadConfig> | null = null;

/** GET /health — cached for the session; falls back to defaults on failure. */
export function getUploadConfig(): Promise<UploadConfig> {
  if (!uploadConfigCache) {
    uploadConfigCache = fetch(`${API_BASE.replace(/\/reconciliation$/, "")}/health`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("health check failed"))))
      .then((body: { upload?: Partial<UploadConfig> }) => ({
        allowedFormats: body.upload?.allowedFormats ?? FALLBACK_UPLOAD_CONFIG.allowedFormats,
        maxBytes: body.upload?.maxBytes ?? FALLBACK_UPLOAD_CONFIG.maxBytes,
      }))
      .catch(() => FALLBACK_UPLOAD_CONFIG);
  }
  return uploadConfigCache;
}

export const DATASET_META: Record<
  DatasetKind,
  { title: string; description: string; accepts: string; demoFile: string }
> = {
  orders: {
    title: "Orders",
    description: "Merchant order and payment records",
    accepts: ".csv,.xlsx,.xls,.json",
    demoFile: "orders.csv",
  },
  settlements: {
    title: "Settlements",
    description: "Razorpay settlement records",
    accepts: ".csv,.xlsx,.xls,.json",
    demoFile: "settlements.csv",
  },
  bank: {
    title: "Bank Statement",
    description: "Bank settlement / credit records",
    accepts: ".csv,.xlsx,.xls,.json",
    demoFile: "bank_statement.csv",
  },
};

interface DatasetFileApiResponse {
  datasetId: string;
  kind: DatasetKind;
  name: string;
  size: number;
  rows: number | null;
  rejected: number;
  status: string;
  progress: number;
  error?: string | null;
  uploadedAt?: string | null;
  checksum?: string | null;
  columnMapping: Record<string, string>;
  unmappedColumns?: string[];
  issues?: Record<string, unknown> | null;
  format?: string;
  detectedKind?: DatasetKind | null;
  detectionConfidence?: number | null;
  warnings?: string[];
}

function mapDatasetResponse(r: DatasetFileApiResponse): DatasetFile {
  return {
    kind: r.kind,
    name: r.name,
    size: r.size,
    rows: r.rows,
    status: r.status === "ready" ? "ready" : r.status === "error" ? "error" : "ready",
    progress: r.progress ?? 100,
    uploadedAt: r.uploadedAt ?? undefined,
    checksum: r.checksum ?? undefined,
    datasetId: r.datasetId,
    format: r.format,
    columnMapping: r.columnMapping,
    unmappedColumns: r.unmappedColumns ?? [],
    detectedKind: r.detectedKind ?? null,
    detectionConfidence: r.detectionConfidence ?? null,
    warnings: r.warnings ?? [],
  };
}

function formatBytesShort(bytes: number): string {
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}

/**
 * Client-side gate mirroring the backend's own validation (`validate_upload`
 * in `app/ingestion/readers.py`) — checked before the file ever leaves the
 * browser, so an obviously-bad upload never round-trips to the server.
 * Returns an error message, or `null` if the file is acceptable.
 */
export async function validateFileBeforeUpload(file: File): Promise<string | null> {
  const config = await getUploadConfig();
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!config.allowedFormats.includes(ext)) {
    return `Unsupported file type.\n\nSupported formats: ${config.allowedFormats.map((f) => f.toUpperCase()).join(", ")}`;
  }
  if (file.size > config.maxBytes) {
    return `File is too large.\n\nMaximum supported size: ${formatBytesShort(config.maxBytes)}`;
  }
  if (file.size === 0) {
    return "This file is empty.";
  }
  return null;
}

/**
 * POST /reconciliation/upload — real multipart upload with byte-level
 * progress via XHR (fetch cannot report upload progress).
 */
export function uploadDataset(
  kind: DatasetKind,
  file: File,
  onProgress: (p: number) => void,
): Promise<DatasetFile> {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    });

    xhr.addEventListener("load", () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // ignore — handled below as an error
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) {
        onProgress(100);
        resolve(mapDatasetResponse(body as DatasetFileApiResponse));
      } else {
        const message =
          (body as { error?: { message?: string } } | null)?.error?.message ??
          `Upload failed with status ${xhr.status}`;
        resolve({
          kind,
          name: file.name,
          size: file.size,
          rows: null,
          status: "error",
          progress: 100,
          error: message,
        });
      }
    });

    xhr.addEventListener("error", () => {
      resolve({
        kind,
        name: file.name,
        size: file.size,
        rows: null,
        status: "error",
        progress: 100,
        error: "Network error while uploading the file.",
      });
    });

    xhr.open("POST", `${API_BASE}/upload`);
    xhr.send(form);
  });
}

/**
 * Loads one of the bundled demo CSVs (served statically from
 * `Frontend/public/demo-data/`) and uploads it through the exact same real
 * upload path used for a user-selected file.
 */
export async function loadDemoDataset(
  kind: DatasetKind,
  onProgress?: (p: number) => void,
): Promise<DatasetFile> {
  const filename = DATASET_META[kind].demoFile;
  const res = await fetch(`/demo-data/${filename}`);
  if (!res.ok) {
    return {
      kind,
      name: filename,
      size: 0,
      rows: null,
      status: "error",
      progress: 100,
      error: `Could not load the bundled demo file (${res.status}).`,
    };
  }
  const blob = await res.blob();
  const file = new File([blob], filename, { type: "text/csv" });
  return uploadDataset(kind, file, onProgress ?? (() => {}));
}

/* ------------------------------------------------------------------ */
/* Job lifecycle                                                       */
/* ------------------------------------------------------------------ */

export async function runReconciliation(input: {
  ordersDatasetId: string;
  settlementsDatasetId: string;
  bankDatasetId?: string;
  source?: string;
}): Promise<{ jobId: string; recordsDetected: number }> {
  const res = await apiFetch<{ jobId: string; status: string; recordsDetected: number }>("/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ordersDatasetId: input.ordersDatasetId,
      settlementsDatasetId: input.settlementsDatasetId,
      bankDatasetId: input.bankDatasetId,
      source: input.source ?? "Manual upload",
    }),
  });
  return { jobId: res.jobId, recordsDetected: res.recordsDetected };
}

/** GET /reconciliation/:jobId/status */
export function getJobStatus(jobId: string): Promise<JobProgress> {
  return apiFetch<JobProgress>(`/${jobId}/status`);
}

/* ------------------------------------------------------------------ */
/* Results                                                             */
/* ------------------------------------------------------------------ */

/** GET /reconciliation/:jobId/results */
export function getResults(jobId: string): Promise<ReconciliationSummary> {
  return apiFetch<ReconciliationSummary>(`/${jobId}/results`);
}

/** GET /reconciliation/:jobId/trend */
export function getTrend(jobId: string): Promise<TrendPoint[]> {
  return apiFetch<TrendPoint[]>(`/${jobId}/trend`);
}

/* ------------------------------------------------------------------ */
/* Transaction table — server-side pagination                          */
/* ------------------------------------------------------------------ */

function queryParams(q: TableQuery) {
  // backend has no date-range filter yet — dropped rather than sent.
  return {
    page: q.page,
    page_size: q.pageSize,
    status: q.status && q.status !== "all" ? q.status : undefined,
    exception_type: q.exceptionType && q.exceptionType !== "all" ? q.exceptionType : undefined,
    search: q.search || undefined,
    sort_by: q.sortBy ?? "orderId",
    sort_dir: q.sortDir ?? "asc",
  };
}

/** GET /reconciliation/:jobId/transactions */
export function getTransactions(jobId: string, q: TableQuery): Promise<TablePage> {
  return apiFetch<TablePage>(`/${jobId}/transactions${qs(queryParams(q))}`);
}

/** GET /reconciliation/:jobId/exceptions */
export function getExceptions(jobId: string, q: TableQuery): Promise<TablePage> {
  return apiFetch<TablePage>(`/${jobId}/exceptions${qs(queryParams(q))}`);
}

/** GET /reconciliation/:jobId/exceptions/:orderId — 404 maps to null. */
export async function getExceptionDetail(jobId: string, orderId: string): Promise<ExceptionDetail | null> {
  try {
    const raw = await apiFetch<{
      transaction: Transaction;
      computed: ExceptionDetail["computed"] & { fee: number; tax: number; refund: number };
      ai: {
        status: string;
        classification: string | null;
        confidence: "high" | "medium" | "low" | null;
        explanation: string | null;
        signals: string[];
        recommendedAction: string | null;
        model: string | null;
        analysedAt: string | null;
        tokens: number;
      };
      evidence: ExceptionDetail["evidence"];
    }>(`/${jobId}/exceptions/${encodeURIComponent(orderId)}`);

    return {
      transaction: raw.transaction,
      computed: raw.computed,
      ai: {
        classification: raw.ai.classification ?? "Pending analysis",
        confidence: raw.ai.confidence ?? "low",
        explanation:
          raw.ai.explanation ??
          (raw.ai.status === "pending"
            ? "The AI layer has not analysed this exception yet."
            : "No explanation is available for this exception."),
        signals: raw.ai.signals ?? [],
        recommendedAction: raw.ai.recommendedAction ?? "Review manually",
        model: raw.ai.model ?? "—",
        analysedAt: raw.ai.analysedAt ?? new Date().toISOString(),
        tokens: raw.ai.tokens ?? 0,
      },
      evidence: raw.evidence,
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

/* ------------------------------------------------------------------ */
/* Audit trail                                                        */
/* ------------------------------------------------------------------ */

/** GET /reconciliation/:jobId/audit — flattened to the row list. */
export async function getAuditTrail(jobId: string, pageSize = 100): Promise<AuditEvent[]> {
  const page = await apiFetch<AuditPage>(`/${jobId}/audit${qs({ page: 1, page_size: pageSize })}`);
  return page.rows;
}

/* ------------------------------------------------------------------ */
/* History                                                             */
/* ------------------------------------------------------------------ */

/** GET /reconciliation/jobs */
export function getHistory(limit = 25): Promise<HistoryEntry[]> {
  return apiFetch<HistoryEntry[]>(`/jobs${qs({ limit })}`);
}

/* ------------------------------------------------------------------ */
/* Export                                                              */
/* ------------------------------------------------------------------ */

/** Relative URL for the CSV export — a plain navigation goes through the Vite proxy. */
export function exportUrl(jobId: string, exceptionsOnly: boolean, limit = 5_000): string {
  return `${API_BASE}/${jobId}/export${qs({ exceptions_only: exceptionsOnly, limit })}`;
}
