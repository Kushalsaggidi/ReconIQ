"""Persistence for jobs, results, exceptions and audit events.

All SQL lives here.  Services and routes deal in domain objects and never write
a query, which is what lets the engine stay database-agnostic.

Writes go through ``bulk_insert_mappings``: at 100k rows, inserting ORM
instances one at a time costs minutes, while a mappings bulk insert costs
seconds.  Reads are always ``LIMIT``ed -- there is no code path that can load a
whole result set into memory.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import AiStatus, AuditEventType, JobStatus, TxnStatus
from app.models.base import utcnow
from app.models.entities import (
    AuditEvent,
    DatasetUpload,
    ExceptionRecord,
    ReconciliationJob,
    TransactionResult,
)
from app.schemas.domain import ReconOutcome

#: Hard ceiling on any page, whatever the client asks for.
MAX_PAGE_SIZE = 500


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

def create_dataset(session: Session, **fields: Any) -> DatasetUpload:
    dataset = DatasetUpload(**fields)
    session.add(dataset)
    session.flush()
    return dataset


def get_dataset(session: Session, dataset_id: str) -> DatasetUpload | None:
    return session.get(DatasetUpload, dataset_id)


def list_datasets(session: Session, limit: int = 50) -> list[DatasetUpload]:
    stmt = select(DatasetUpload).order_by(DatasetUpload.created_at.desc()).limit(limit)
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def create_job(session: Session, job_id: str, **fields: Any) -> ReconciliationJob:
    job = ReconciliationJob(id=job_id, **fields)
    session.add(job)
    session.flush()
    return job


def get_job(session: Session, job_id: str) -> ReconciliationJob | None:
    return session.get(ReconciliationJob, job_id)


def list_jobs(session: Session, limit: int = 25) -> list[ReconciliationJob]:
    stmt = (
        select(ReconciliationJob)
        .order_by(ReconciliationJob.created_at.desc())
        .limit(min(limit, MAX_PAGE_SIZE))
    )
    return list(session.scalars(stmt))


def update_job(session: Session, job_id: str, **fields: Any) -> None:
    job = session.get(ReconciliationJob, job_id)
    if job is None:
        return
    for key, value in fields.items():
        setattr(job, key, value)
    session.flush()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

def _txn_mapping(job_id: str, outcome: ReconOutcome) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "order_id": outcome.order_id,
        "payment_id": outcome.payment_id,
        "settlement_id": outcome.settlement_id,
        "bank_reference": outcome.bank_reference,
        "expected_amount": outcome.expected_amount,
        "settled_amount": outcome.settled_amount,
        "difference": outcome.difference,
        "fee": outcome.fee,
        "tax": outcome.tax,
        "refund": outcome.refund,
        "adjustment": outcome.adjustment,
        "accounted_for": outcome.accounted_for,
        "unexplained": outcome.unexplained,
        "status": outcome.status.value,
        "exception_type": outcome.exception_type.value if outcome.exception_type else None,
        "cause": outcome.cause.value if outcome.cause else None,
        "confidence": outcome.confidence.value,
        "reason": outcome.reason,
        "currency": outcome.currency,
        "method": outcome.method,
        "order_date": outcome.order_date,
        "settlement_date": outcome.settlement_date,
    }


def _exception_mapping(job_id: str, outcome: ReconOutcome) -> dict[str, Any]:
    from app.models.base import new_id

    return {
        "id": new_id("exc"),
        "job_id": job_id,
        "order_id": outcome.order_id,
        "payment_id": outcome.payment_id,
        "settlement_id": outcome.settlement_id,
        "expected_amount": outcome.expected_amount,
        "actual_amount": outcome.settled_amount,
        "difference": outcome.difference,
        "fee": outcome.fee,
        "tax": outcome.tax,
        "refund": outcome.refund,
        "adjustment": outcome.adjustment,
        "accounted_for": outcome.accounted_for,
        "unexplained": outcome.unexplained,
        "currency": outcome.currency,
        "exception_type": outcome.exception_type.value if outcome.exception_type else "unresolved",
        "cause": outcome.cause.value if outcome.cause else None,
        "confidence": outcome.confidence.value,
        "status": "open",
        "reason": outcome.reason,
        "evidence": [e.to_dict() for e in outcome.evidence],
        "checks": [c.to_dict() for c in outcome.checks],
        "ai_status": AiStatus.PENDING.value,
        # An unresolved record is by definition beyond deterministic
        # explanation, so it is queued for a human from the moment it is
        # written -- regardless of anything the AI layer later says.
        "requires_human_review": outcome.status is TxnStatus.UNRESOLVED,
        "created_at": utcnow(),
    }


def persist_outcomes(session: Session, job_id: str, outcomes: Sequence[ReconOutcome]) -> int:
    """Write one batch of results.  Returns the number of exceptions written."""
    if not outcomes:
        return 0
    session.bulk_insert_mappings(
        TransactionResult, [_txn_mapping(job_id, o) for o in outcomes]  # type: ignore[arg-type]
    )
    exception_rows = [_exception_mapping(job_id, o) for o in outcomes if o.is_exception]
    if exception_rows:
        session.bulk_insert_mappings(ExceptionRecord, exception_rows)  # type: ignore[arg-type]
    session.flush()
    return len(exception_rows)


# ---------------------------------------------------------------------------
# Paginated reads
# ---------------------------------------------------------------------------

_SORTABLE = {
    "orderId": TransactionResult.order_id,
    "expected": TransactionResult.expected_amount,
    "settled": TransactionResult.settled_amount,
    "difference": TransactionResult.difference,
    "settlementDate": TransactionResult.settlement_date,
}


def query_transactions(
    session: Session,
    job_id: str,
    *,
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    exception_type: str | None = None,
    search: str | None = None,
    exceptions_only: bool = False,
    sort_by: str = "orderId",
    sort_dir: str = "asc",
) -> dict[str, Any]:
    """One page of results, plus the facet counts the UI chips display."""
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))

    # `base` is every filter except status. Facet counts are computed over
    # `base` so each chip shows how many rows sit behind it, rather than
    # collapsing to whichever status is currently selected.
    base = [TransactionResult.job_id == job_id]
    if exceptions_only:
        base.append(TransactionResult.status != TxnStatus.MATCHED.value)
    if exception_type and exception_type != "all":
        base.append(TransactionResult.exception_type == exception_type)
    if search:
        like = f"%{search.strip()}%"
        base.append(
            or_(
                TransactionResult.order_id.ilike(like),
                TransactionResult.payment_id.ilike(like),
                TransactionResult.settlement_id.ilike(like),
                TransactionResult.bank_reference.ilike(like),
            )
        )

    filters = list(base)
    if status and status != "all":
        filters.append(TransactionResult.status == status)

    total = session.scalar(
        select(func.count()).select_from(TransactionResult).where(*filters)
    ) or 0

    column = _SORTABLE.get(sort_by, TransactionResult.order_id)
    order = column.desc() if sort_dir == "desc" else column.asc()
    rows = list(
        session.scalars(
            select(TransactionResult)
            .where(*filters)
            .order_by(order, TransactionResult.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    facet_rows = session.execute(
        select(TransactionResult.status, func.count())
        .where(*base)
        .group_by(TransactionResult.status)
    ).all()
    facets = {"matched": 0, "exception": 0, "unresolved": 0}
    for value, count in facet_rows:
        if value in facets:
            facets[value] = count

    return {
        "rows": rows,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
        "facets": facets,
    }


def get_exception(session: Session, job_id: str, order_id: str) -> ExceptionRecord | None:
    stmt = select(ExceptionRecord).where(
        ExceptionRecord.job_id == job_id, ExceptionRecord.order_id == order_id
    )
    return session.scalars(stmt).first()


def get_transaction(session: Session, job_id: str, order_id: str) -> TransactionResult | None:
    stmt = select(TransactionResult).where(
        TransactionResult.job_id == job_id, TransactionResult.order_id == order_id
    )
    return session.scalars(stmt).first()


def iter_exceptions_for_ai(
    session: Session, job_id: str, limit: int
) -> list[ExceptionRecord]:
    """The bounded slice of exceptions the AI layer is allowed to see.

    Ordered by unexplained magnitude: if we can only afford to explain some of
    them, explain the expensive ones.  This is also the guarantee that we never
    stream a whole dataset to a model.
    """
    stmt = (
        select(ExceptionRecord)
        .where(
            ExceptionRecord.job_id == job_id,
            ExceptionRecord.ai_status == AiStatus.PENDING.value,
        )
        .order_by(func.abs(ExceptionRecord.unexplained).desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def update_exception_ai(session: Session, exception_id: str, **fields: Any) -> None:
    record = session.get(ExceptionRecord, exception_id)
    if record is None:
        return
    for key, value in fields.items():
        setattr(record, key, value)
    session.flush()


def get_largest_variances(session: Session, job_id: str, limit: int = 5) -> list[TransactionResult]:
    """Exceptions/unresolved rows ordered by |unexplained| descending.

    Used by the Copilot's "largest variances" tool -- same ranking the AI
    analyser itself uses to prioritise which exceptions matter most.
    """
    stmt = (
        select(TransactionResult)
        .where(
            TransactionResult.job_id == job_id,
            TransactionResult.status != TxnStatus.MATCHED.value,
        )
        .order_by(func.abs(TransactionResult.unexplained).desc())
        .limit(min(limit, MAX_PAGE_SIZE))
    )
    return list(session.scalars(stmt))


def get_human_review_exceptions(
    session: Session, job_id: str, limit: int = 10
) -> list[ExceptionRecord]:
    """Exceptions flagged for a human, largest unexplained residual first."""
    stmt = (
        select(ExceptionRecord)
        .where(
            ExceptionRecord.job_id == job_id,
            ExceptionRecord.requires_human_review.is_(True),
        )
        .order_by(func.abs(ExceptionRecord.unexplained).desc())
        .limit(min(limit, MAX_PAGE_SIZE))
    )
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def write_audit(
    session: Session,
    job_id: str | None,
    event_type: AuditEventType,
    message: str,
    *,
    entity_id: str | None = None,
    actor: str = "Engine",
    engine: str = "deterministic",
    severity: str = "ok",
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> None:
    session.add(
        AuditEvent(
            job_id=job_id,
            event_type=event_type.value,
            message=message,
            entity_id=entity_id,
            actor=actor,
            engine=engine,
            severity=severity,
            event_metadata=metadata,
            created_at=created_at or utcnow(),
        )
    )


def write_audit_batch(session: Session, rows: Iterable[dict[str, Any]]) -> None:
    payload = list(rows)
    if payload:
        session.bulk_insert_mappings(AuditEvent, payload)  # type: ignore[arg-type]


def query_audit(
    session: Session,
    job_id: str,
    *,
    page: int = 1,
    page_size: int = 100,
    event_type: str | None = None,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    filters = [AuditEvent.job_id == job_id]
    if event_type:
        filters.append(AuditEvent.event_type == event_type)
    total = session.scalar(
        select(func.count()).select_from(AuditEvent).where(*filters)
    ) or 0
    rows = list(
        session.scalars(
            select(AuditEvent)
            .where(*filters)
            .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }


def job_status_counts(session: Session, job_id: str) -> dict[str, int]:
    rows = session.execute(
        select(TransactionResult.status, func.count())
        .where(TransactionResult.job_id == job_id)
        .group_by(TransactionResult.status)
    ).all()
    return {status: count for status, count in rows}


def purge_job(session: Session, job_id: str) -> None:
    """Delete a job and everything hanging off it.  Used by tests."""
    for model in (TransactionResult, ExceptionRecord, AuditEvent):
        session.query(model).filter(model.job_id == job_id).delete()
    job = session.get(ReconciliationJob, job_id)
    if job is not None:
        session.delete(job)


__all__ = [
    "MAX_PAGE_SIZE",
    "JobStatus",
    "create_dataset",
    "create_job",
    "get_dataset",
    "get_exception",
    "get_human_review_exceptions",
    "get_job",
    "get_largest_variances",
    "get_transaction",
    "iter_exceptions_for_ai",
    "list_datasets",
    "list_jobs",
    "persist_outcomes",
    "purge_job",
    "query_audit",
    "query_transactions",
    "update_exception_ai",
    "update_job",
    "write_audit",
    "write_audit_batch",
]
