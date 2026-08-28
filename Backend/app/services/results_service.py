"""Read-side services: ORM rows -> API responses.

All the mapping between storage shape and contract shape lives here, so the
routes stay thin and the ORM never leaks into a response model.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import (
    AUTO_EXPLAINED_BUCKETS,
    BUCKET_ORDER,
    EXCEPTION_LABELS,
    AiStatus,
    DatasetKind,
    ExceptionType,
    JobStatus,
)
from app.core.errors import ErrorCode, NotFoundError
from app.models.base import utcnow
from app.models.entities import (
    AuditEvent,
    ExceptionRecord,
    ReconciliationJob,
    TransactionResult,
)
from app.schemas.api import (
    AiAnalysisResponse,
    AuditEventResponse,
    AuditPage,
    CheckResponse,
    ComputedResponse,
    DatasetSummary,
    EvidenceFieldResponse,
    EvidenceRecordResponse,
    ExceptionBreakdown,
    ExceptionBucketResponse,
    ExceptionDetailResponse,
    Facets,
    HistoryEntryResponse,
    JobProgressResponse,
    ReconciliationSummaryResponse,
    StageStateResponse,
    TransactionPage,
    TransactionResponse,
    TrendPointResponse,
)
from app.storage import repository as repo

#: Stage weights used to turn "which stage are we on" into a percentage. They
#: reflect measured cost: matching dominates, so it owns most of the bar.
_STAGE_WEIGHT: dict[str, tuple[float, float]] = {
    "validate": (0.00, 0.08),
    "normalize": (0.08, 0.16),
    "match": (0.16, 0.70),
    "detect": (0.70, 0.80),
    "ai": (0.80, 0.94),
    "finalize": (0.94, 1.00),
}


def require_job(session: Session, job_id: str) -> ReconciliationJob:
    job = repo.get_job(session, job_id)
    if job is None:
        raise NotFoundError(
            f"No reconciliation job with id '{job_id}'.",
            code=ErrorCode.JOB_NOT_FOUND,
            status_code=404,
        )
    return job


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

def _percent(job: ReconciliationJob) -> float:
    if job.status == JobStatus.COMPLETED.value:
        return 100.0
    if job.status in (JobStatus.QUEUED.value, JobStatus.FAILED.value):
        return 0.0 if job.status == JobStatus.QUEUED.value else 100.0
    low, high = _STAGE_WEIGHT.get(job.stage or "validate", (0.0, 0.08))
    within = 0.0
    if job.stage == "match" and job.records_detected:
        within = min(1.0, job.records_processed / job.records_detected)
    return round((low + (high - low) * within) * 100, 2)


def build_progress(job: ReconciliationJob) -> JobProgressResponse:
    now = utcnow()
    started = job.started_at or job.created_at
    finished = job.completed_at or now
    elapsed_ms = max(0, int((finished - started).total_seconds() * 1000))
    percent = _percent(job)
    stages = [StageStateResponse(**s) for s in (job.stages or [])]
    active = next((s for s in stages if s.status == "active"), None)

    rate = int(job.records_processed / (elapsed_ms / 1000)) if elapsed_ms > 400 else 0
    remaining = max(0, job.records_detected - job.records_processed)
    eta = int(remaining / rate * 1000) if rate else 0

    if job.status == JobStatus.COMPLETED.value:
        label = "Completed"
    elif job.status == JobStatus.FAILED.value:
        label = "Failed"
    elif active is not None:
        label = active.label
    else:
        label = "Queued"

    return JobProgressResponse(
        jobId=job.id,
        status=JobStatus(job.status),
        recordsDetected=job.records_detected,
        recordsProcessed=job.records_processed,
        matchedSoFar=job.matched_so_far,
        exceptionsSoFar=job.exceptions_so_far,
        ratePerSecond=rate,
        elapsedMs=elapsed_ms,
        etaMs=eta,
        percent=percent,
        stages=stages,
        currentStageLabel=label,
        error=job.error_message,
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _buckets_from(metrics: dict[str, Any] | None) -> list[ExceptionBucketResponse]:
    stored = {b["type"]: b for b in (metrics or {}).get("buckets", [])}
    return [
        ExceptionBucketResponse(
            type=b,
            label=EXCEPTION_LABELS[b],
            count=stored.get(b.value, {}).get("count", 0),
            amount=stored.get(b.value, {}).get("amount", 0),
            autoExplained=b in AUTO_EXPLAINED_BUCKETS,
        )
        for b in BUCKET_ORDER
    ]


def build_summary(session: Session, job: ReconciliationJob) -> ReconciliationSummaryResponse:
    metrics = job.metrics or {}
    report = job.validation_report or {}
    datasets: list[DatasetSummary] = []
    for kind in DatasetKind:
        entry = report.get(kind.value) if isinstance(report, dict) else None
        if isinstance(entry, dict):
            datasets.append(
                DatasetSummary(
                    kind=kind,
                    name=entry.get("sourceName") or kind.value,
                    rows=int(entry.get("rows") or 0),
                )
            )

    return ReconciliationSummaryResponse(
        jobId=job.id,
        createdAt=job.created_at,
        completedAt=job.completed_at,
        durationMs=job.duration_ms,
        status=JobStatus(job.status),
        recordsProcessed=job.total_records,
        matched=job.matched_records,
        exceptions=job.exception_records,
        unresolved=job.unresolved_records,
        matchRate=job.match_rate,
        grossValue=job.gross_value,
        settledValue=job.settled_value,
        varianceValue=job.variance_value,
        currency=job.currency,
        buckets=_buckets_from(metrics),
        breakdown=ExceptionBreakdown(**(metrics.get("breakdown") or {})),
        datasets=datasets,
        aiStatus=AiStatus(job.ai_status),
        aiAnalysedCount=job.ai_analysed_count,
        error=job.error_message,
    )


def build_trend(job: ReconciliationJob) -> list[TrendPointResponse]:
    return [TrendPointResponse(**p) for p in (job.metrics or {}).get("trend", [])]


def build_history(jobs: list[ReconciliationJob]) -> list[HistoryEntryResponse]:
    return [
        HistoryEntryResponse(
            jobId=j.id,
            createdAt=j.created_at,
            recordsProcessed=j.total_records,
            matched=j.matched_records,
            exceptions=j.exception_records + j.unresolved_records,
            matchRate=j.match_rate,
            status=JobStatus(j.status),
            durationMs=j.duration_ms,
            source=j.source,
        )
        for j in jobs
    ]


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def to_transaction(row: TransactionResult) -> TransactionResponse:
    return TransactionResponse(
        orderId=row.order_id,
        paymentId=row.payment_id,
        settlementId=row.settlement_id,
        bankRef=row.bank_reference,
        expected=row.expected_amount,
        settled=row.settled_amount,
        difference=row.difference,
        fee=row.fee,
        tax=row.tax,
        refund=row.refund,
        accountedFor=row.accounted_for,
        unexplained=row.unexplained,
        status=row.status,
        exceptionType=ExceptionType(row.exception_type) if row.exception_type else None,
        reason=row.reason,
        currency=row.currency,
        settlementDate=row.settlement_date,
        capturedAt=row.order_date,
        method=row.method,
    )


def build_transaction_page(payload: dict[str, Any]) -> TransactionPage:
    return TransactionPage(
        rows=[to_transaction(r) for r in payload["rows"]],
        total=payload["total"],
        page=payload["page"],
        pageSize=payload["pageSize"],
        totalPages=payload["totalPages"],
        facets=Facets(**payload["facets"]),
    )


# ---------------------------------------------------------------------------
# Exception detail
# ---------------------------------------------------------------------------

def build_exception_detail(
    session: Session, job_id: str, order_id: str
) -> ExceptionDetailResponse:
    record = repo.get_exception(session, job_id, order_id)
    if record is None:
        raise NotFoundError(
            f"No exception for order '{order_id}' in job '{job_id}'.",
            status_code=404,
        )
    txn = repo.get_transaction(session, job_id, order_id)
    if txn is None:  # pragma: no cover - written in the same transaction
        raise NotFoundError(f"No transaction row for order '{order_id}'.", status_code=404)

    evidence = [
        EvidenceRecordResponse(
            source=item.get("source", ""),
            recordId=item.get("recordId"),
            present=bool(item.get("present")),
            fields=[
                EvidenceFieldResponse(label=f.get("label", ""), value=str(f.get("value", "")))
                for f in item.get("fields", [])
            ],
        )
        for item in (record.evidence or [])
    ]

    return ExceptionDetailResponse(
        exceptionId=record.id,
        transaction=to_transaction(txn),
        computed=ComputedResponse(
            expected=record.expected_amount,
            settled=record.actual_amount,
            difference=record.difference,
            fee=record.fee,
            tax=record.tax,
            refund=record.refund,
            accountedFor=record.accounted_for,
            unexplained=record.unexplained,
            checks=[CheckResponse(**c) for c in (record.checks or [])],
        ),
        ai=AiAnalysisResponse(
            status=AiStatus(record.ai_status),
            classification=record.ai_classification,
            confidence=record.ai_confidence,
            explanation=record.ai_explanation,
            signals=list(record.ai_signals or []),
            recommendedAction=record.ai_recommended_action,
            model=record.ai_model,
            analysedAt=record.ai_analysed_at,
            tokens=record.ai_tokens,
            error=record.ai_error,
            requiresHumanReview=record.requires_human_review,
        ),
        evidence=evidence,
        createdAt=record.created_at,
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

#: Event type -> human title. The message carries the detail.
_AUDIT_TITLES: dict[str, str] = {
    "DATASET_UPLOADED": "Dataset uploaded",
    "DATASET_VALIDATED": "Dataset validated",
    "DATASET_NORMALIZED": "Data normalised",
    "DATASET_REJECTED": "Dataset rejected",
    "RECONCILIATION_STARTED": "Reconciliation job created",
    "BATCH_PROCESSED": "Batch processed",
    "RECORD_MATCHED": "Records reconciled",
    "EXCEPTION_DETECTED": "Exceptions detected",
    "AI_ANALYSIS_STARTED": "Exception analysis started",
    "AI_ANALYSIS_COMPLETED": "Exception analysis completed",
    "AI_ANALYSIS_FAILED": "Exception analysis unavailable",
    "AI_ANALYSIS_SKIPPED": "Exception analysis skipped",
    "RECONCILIATION_COMPLETED": "Report generated",
    "RECONCILIATION_FAILED": "Reconciliation failed",
    "HUMAN_REVIEW_REQUIRED": "Flagged for human review",
}


def to_audit_event(row: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        id=str(row.id),
        at=row.created_at,
        title=_AUDIT_TITLES.get(row.event_type, row.event_type.replace("_", " ").title()),
        description=row.message,
        actor=row.actor,
        engine=row.engine,
        status=row.severity,
        entityId=row.entity_id,
        meta=row.event_metadata,
    )


def build_audit_page(payload: dict[str, Any]) -> AuditPage:
    return AuditPage(
        rows=[to_audit_event(r) for r in payload["rows"]],
        total=payload["total"],
        page=payload["page"],
        pageSize=payload["pageSize"],
        totalPages=payload["totalPages"],
    )


def export_rows(session: Session, job_id: str, *, exceptions_only: bool, limit: int) -> str:
    """Stream-friendly CSV export.

    Paged internally so a large export never materialises the full result set.
    """
    from app.core.money import to_major

    header = (
        "order_id,payment_id,settlement_id,bank_reference,expected_amount,"
        "settled_amount,difference,fee,tax,refund,unexplained,status,"
        "exception_type,reason,settlement_date\n"
    )
    lines = [header]
    page = 1
    written = 0
    page_size = 500
    while written < limit:
        payload = repo.query_transactions(
            session, job_id, page=page, page_size=page_size,
            exceptions_only=exceptions_only,
        )
        rows = payload["rows"]
        if not rows:
            break
        for r in rows:
            if written >= limit:
                break
            reason = r.reason.replace('"', "'")
            lines.append(
                f"{r.order_id},{r.payment_id},{r.settlement_id or ''},"
                f"{r.bank_reference or ''},{to_major(r.expected_amount)},"
                f"{to_major(r.settled_amount)},{to_major(r.difference)},"
                f"{to_major(r.fee)},{to_major(r.tax)},{to_major(r.refund)},"
                f"{to_major(r.unexplained)},{r.status},{r.exception_type or ''},"
                f'"{reason}",{r.settlement_date.date() if r.settlement_date else ""}\n'
            )
            written += 1
        if len(rows) < page_size:
            break
        page += 1
    return "".join(lines)


