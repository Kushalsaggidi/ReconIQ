"""Public API response models.

These mirror `Frontend/src/services/types.ts` field-for-field, deliberately:

* camelCase keys,
* amounts as **integer paise**, so the UI formats without float drift,
* the same lowercase enum strings.

That makes swapping the frontend's `mockApi` for `fetch` a one-file change with
no component edits.  Treat every field name here as a published contract --
adding is safe, renaming is not.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    AiStatus,
    Confidence,
    DatasetKind,
    ExceptionType,
    JobStatus,
    TxnStatus,
)

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

class DatasetFileResponse(ApiModel):
    datasetId: str
    kind: DatasetKind
    name: str
    size: int
    rows: int | None = None
    rejected: int = 0
    status: str = "ready"
    progress: int = 100
    error: str | None = None
    uploadedAt: datetime | None = None
    checksum: str | None = None
    columnMapping: dict[str, str] = Field(default_factory=dict)
    #: Column headers present in the file that we did not recognise. Surfaced
    #: so an operator can tell "ignored" apart from "silently dropped".
    unmappedColumns: list[str] = Field(default_factory=list)
    issues: dict[str, Any] | None = None
    #: File format the upload was parsed as, e.g. "csv", "xlsx", "json".
    format: str = "csv"
    #: Dataset kind the headers most resemble -- a cross-check against `kind`,
    #: surfaced so the UI can flag "this looks like settlements, not orders".
    detectedKind: DatasetKind | None = None
    detectionConfidence: float | None = None
    warnings: list[str] = Field(default_factory=list)
    #: True once the file has no blocking issues and can be used in a run.
    ready: bool = True


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    ordersDatasetId: str
    settlementsDatasetId: str
    bankDatasetId: str | None = None
    source: str = "Manual upload"


class RunResponse(ApiModel):
    jobId: str
    status: JobStatus
    recordsDetected: int = 0


class StageStateResponse(ApiModel):
    id: str
    label: str
    detail: str
    engine: str
    status: str
    startedAt: str | None = None
    finishedAt: str | None = None


class JobProgressResponse(ApiModel):
    jobId: str
    status: JobStatus
    recordsDetected: int
    recordsProcessed: int
    matchedSoFar: int
    exceptionsSoFar: int
    ratePerSecond: int
    elapsedMs: int
    etaMs: int
    percent: float
    stages: list[StageStateResponse]
    currentStageLabel: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

class ExceptionBucketResponse(ApiModel):
    type: ExceptionType
    label: str
    count: int
    amount: int
    autoExplained: bool


class DatasetSummary(ApiModel):
    kind: DatasetKind
    name: str
    rows: int


class ExceptionBreakdown(ApiModel):
    partial_payment_count: int = 0
    refund_count: int = 0
    fee_tax_count: int = 0
    rounding_count: int = 0
    unresolved_count: int = 0


class ReconciliationSummaryResponse(ApiModel):
    jobId: str
    createdAt: datetime
    completedAt: datetime | None = None
    durationMs: int
    status: JobStatus
    recordsProcessed: int
    matched: int
    exceptions: int
    unresolved: int
    matchRate: float
    #: All values in minor units (paise).
    grossValue: int
    settledValue: int
    varianceValue: int
    currency: str = "INR"
    buckets: list[ExceptionBucketResponse]
    breakdown: ExceptionBreakdown
    datasets: list[DatasetSummary] = Field(default_factory=list)
    aiStatus: AiStatus = AiStatus.PENDING
    aiAnalysedCount: int = 0
    error: str | None = None


class TrendPointResponse(ApiModel):
    date: str
    label: str
    processed: int
    matched: int
    exceptions: int
    matchRate: float


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

class TransactionResponse(ApiModel):
    orderId: str
    paymentId: str
    settlementId: str | None = None
    bankRef: str | None = None
    expected: int
    settled: int
    difference: int
    fee: int
    tax: int
    refund: int
    accountedFor: int
    unexplained: int
    status: TxnStatus
    exceptionType: ExceptionType | None = None
    reason: str = ""
    currency: str = "INR"
    settlementDate: datetime | None = None
    capturedAt: datetime | None = None
    method: str | None = None


class Facets(ApiModel):
    matched: int = 0
    exception: int = 0
    unresolved: int = 0


class Page(ApiModel, Generic[T]):
    rows: list[T]
    total: int
    page: int
    pageSize: int
    totalPages: int


class TransactionPage(ApiModel):
    rows: list[TransactionResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int
    facets: Facets


# ---------------------------------------------------------------------------
# Exception detail
# ---------------------------------------------------------------------------

class EvidenceFieldResponse(ApiModel):
    label: str
    value: str


class EvidenceRecordResponse(ApiModel):
    source: str
    recordId: str | None = None
    present: bool
    fields: list[EvidenceFieldResponse] = Field(default_factory=list)


class CheckResponse(ApiModel):
    label: str
    passed: bool
    detail: str


class ComputedResponse(ApiModel):
    """Every figure here came from the deterministic engine."""

    expected: int
    settled: int
    difference: int
    fee: int
    tax: int
    refund: int
    accountedFor: int
    unexplained: int
    checks: list[CheckResponse] = Field(default_factory=list)


class AiAnalysisResponse(ApiModel):
    """Advisory only.  ``status`` tells the UI whether to trust or hide it."""

    status: AiStatus
    classification: str | None = None
    confidence: Confidence | None = None
    explanation: str | None = None
    signals: list[str] = Field(default_factory=list)
    recommendedAction: str | None = None
    model: str | None = None
    analysedAt: datetime | None = None
    tokens: int = 0
    error: str | None = None
    requiresHumanReview: bool = False


class ExceptionDetailResponse(ApiModel):
    exceptionId: str
    transaction: TransactionResponse
    computed: ComputedResponse
    ai: AiAnalysisResponse
    evidence: list[EvidenceRecordResponse] = Field(default_factory=list)
    createdAt: datetime


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditEventResponse(ApiModel):
    id: str
    at: datetime
    title: str
    description: str
    actor: str
    engine: str
    status: str
    entityId: str | None = None
    meta: dict[str, Any] | None = None


class AuditPage(ApiModel):
    rows: list[AuditEventResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int


class HistoryEntryResponse(ApiModel):
    jobId: str
    createdAt: datetime
    recordsProcessed: int
    matched: int
    exceptions: int
    matchRate: float
    status: JobStatus
    durationMs: int
    source: str


# ---------------------------------------------------------------------------
# Copilot -- read-only, grounded Q&A over one job. See app/copilot/.
# ---------------------------------------------------------------------------

class CopilotMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class CopilotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversationId: str | None = None
    #: Prior turns for this conversation, oldest first. The Copilot endpoint
    #: is stateless -- there is no server-side chat store -- so the caller
    #: replays history; the backend caps how much of it is actually used.
    history: list[CopilotMessage] = Field(default_factory=list)


class CopilotToolCallSummary(ApiModel):
    tool: str
    ok: bool


class CopilotSource(ApiModel):
    label: str
    tool: str


class CopilotResponse(ApiModel):
    answer: str
    #: "ok" | "provider_unavailable" | "validation_failed". Kept as a plain
    #: str (not an enum) so a future status value never breaks older clients.
    status: str = "ok"
    #: False whenever `answer` is a safe fallback substituted because the
    #: model's own response failed grounding, or the provider was unavailable.
    validated: bool = True
    sources: list[CopilotSource] = Field(default_factory=list)
    toolCalls: list[CopilotToolCallSummary] = Field(default_factory=list)
    model: str | None = None


class HealthResponse(ApiModel):
    status: str
    environment: str
    database: str
    ai: dict[str, Any]
    upload: dict[str, Any] = Field(default_factory=dict)
    version: str = "1.0.0"
