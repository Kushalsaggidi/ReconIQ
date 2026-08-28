/**
 * Domain types shared by the mock service layer and the UI.
 * These mirror the payloads the Python reconciliation service will return, so
 * swapping `mockApi` for `httpApi` requires no component changes.
 */

export type DatasetKind = "orders" | "settlements" | "bank";

export type UploadStatus = "empty" | "uploading" | "ready" | "error";

export interface DatasetFile {
  kind: DatasetKind;
  name: string;
  size: number;
  rows: number | null;
  status: UploadStatus;
  progress: number;
  error?: string;
  uploadedAt?: string;
  checksum?: string;
  isDemo?: boolean;
}

export type TxnStatus = "matched" | "exception" | "unresolved";

export type ExceptionType =
  | "partial_payment"
  | "refund"
  | "fee_tax"
  | "rounding"
  | "unresolved";

export type Confidence = "high" | "medium" | "low";

/** Amounts are integers in paise — no float drift in a reconciliation product. */
export interface Transaction {
  orderId: string;
  paymentId: string;
  settlementId: string | null;
  bankRef: string | null;
  expected: number;
  settled: number;
  difference: number;
  fee: number;
  tax: number;
  refund: number;
  status: TxnStatus;
  exceptionType: ExceptionType | null;
  reason: string;
  settlementDate: string;
  capturedAt: string;
  method: "UPI" | "Card" | "Netbanking" | "Wallet";
}

export interface EvidenceField {
  label: string;
  value: string;
  emphasis?: boolean;
}

export interface EvidenceRecord {
  source: "Orders dataset" | "Razorpay settlement" | "Bank statement" | "Refund ledger";
  recordId: string;
  present: boolean;
  fields: EvidenceField[];
}

/** The AI layer only ever classifies and explains — never computes a figure. */
export interface AiAnalysis {
  classification: string;
  confidence: Confidence;
  explanation: string;
  signals: string[];
  recommendedAction: string;
  model: string;
  analysedAt: string;
  tokens: number;
}

export interface ExceptionDetail {
  transaction: Transaction;
  /** Every number here was produced by the deterministic engine. */
  computed: {
    expected: number;
    settled: number;
    difference: number;
    accountedFor: number;
    unexplained: number;
    checks: { label: string; passed: boolean; detail: string }[];
  };
  ai: AiAnalysis;
  evidence: EvidenceRecord[];
}

export type JobStage =
  | "validate"
  | "normalize"
  | "match"
  | "detect"
  | "ai"
  | "finalize";

export interface StageState {
  id: JobStage;
  label: string;
  detail: string;
  engine: "deterministic" | "ai";
  status: "pending" | "active" | "done";
  startedAt?: string;
  finishedAt?: string;
}

export type JobStatus = "queued" | "running" | "completed" | "failed";

export interface JobProgress {
  jobId: string;
  status: JobStatus;
  recordsDetected: number;
  recordsProcessed: number;
  matchedSoFar: number;
  exceptionsSoFar: number;
  ratePerSecond: number;
  elapsedMs: number;
  etaMs: number;
  percent: number;
  stages: StageState[];
  currentStageLabel: string;
}

export interface ExceptionBucket {
  type: ExceptionType;
  label: string;
  count: number;
  amount: number;
  autoExplained: boolean;
}

export interface ReconciliationSummary {
  jobId: string;
  createdAt: string;
  completedAt: string;
  durationMs: number;
  status: JobStatus;
  recordsProcessed: number;
  matched: number;
  exceptions: number;
  unresolved: number;
  matchRate: number;
  grossValue: number;
  settledValue: number;
  varianceValue: number;
  buckets: ExceptionBucket[];
  datasets: { kind: DatasetKind; name: string; rows: number }[];
}

export interface AuditEvent {
  id: string;
  at: string;
  title: string;
  description: string;
  actor: "Engine" | "AI Analyst" | "User" | "System";
  engine: "deterministic" | "ai" | "system";
  status: "ok" | "info" | "warning";
  meta?: Record<string, string>;
}

export interface TrendPoint {
  date: string;
  label: string;
  processed: number;
  matched: number;
  exceptions: number;
  matchRate: number;
}

export interface TableQuery {
  page: number;
  pageSize: number;
  search?: string;
  status?: TxnStatus | "all";
  exceptionType?: ExceptionType | "all";
  dateRange?: "all" | "7d" | "14d" | "30d";
  sortBy?: "orderId" | "expected" | "settled" | "difference" | "settlementDate";
  sortDir?: "asc" | "desc";
}

export interface TablePage {
  rows: Transaction[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  facets: { matched: number; exception: number; unresolved: number };
}

export interface HistoryEntry {
  jobId: string;
  createdAt: string;
  recordsProcessed: number;
  matched: number;
  exceptions: number;
  matchRate: number;
  status: JobStatus;
  durationMs: number;
  source: string;
}

export interface ActivityItem {
  id: string;
  at: string;
  title: string;
  detail: string;
  kind: "job" | "exception" | "ai" | "upload" | "user";
}
