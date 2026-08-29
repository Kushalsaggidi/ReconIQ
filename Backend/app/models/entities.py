"""ORM entities.

Five tables:

``datasets``            one uploaded file, its checksum and validation report
``reconciliation_jobs`` job metadata, status, aggregate metrics
``transaction_results`` one row per reconciled record (the big table)
``exception_records``   the subset needing attention, plus advisory AI output
``audit_events``        append-only narrative of what the system did

Indexes are chosen for the queries the API actually issues: every result screen
filters by ``job_id`` first, then by status / exception type / identifier.
Without the composite indexes those become full scans, which is the difference
between a 40 ms page and a 12 s page at a million rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AiStatus, JobStatus
from app.models.base import Base, Money, new_id, utcnow


class DatasetUpload(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True,
                                    default=lambda: new_id("ds"))
    kind: Mapped[str] = mapped_column(String(24), index=True)
    original_name: Mapped[str] = mapped_column(String(512))
    #: Path/key in the file store. Raw files are never stored in the database.
    storage_key: Mapped[str] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(96), nullable=True)
    column_mapping: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    validation_report: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="ready")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class ReconciliationJob(Base):
    __tablename__ = "reconciliation_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default=JobStatus.QUEUED.value, index=True)
    stage: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source: Mapped[str] = mapped_column(String(128), default="Manual upload")

    orders_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id"), nullable=True
    )
    settlements_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id"), nullable=True
    )
    bank_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("datasets.id"), nullable=True
    )

    # -- progress (updated during the run so the UI can show a live bar) ---
    records_detected: Mapped[int] = mapped_column(Integer, default=0)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    matched_so_far: Mapped[int] = mapped_column(Integer, default=0)
    exceptions_so_far: Mapped[int] = mapped_column(Integer, default=0)
    stages: Mapped[list[Any] | None] = mapped_column(nullable=True)

    # -- final metrics -----------------------------------------------------
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    matched_records: Mapped[int] = mapped_column(Integer, default=0)
    exception_records: Mapped[int] = mapped_column(Integer, default=0)
    unresolved_records: Mapped[int] = mapped_column(Integer, default=0)
    match_rate: Mapped[float] = mapped_column(Float, default=0.0)
    gross_value: Mapped[int] = mapped_column(Money, default=0)
    settled_value: Mapped[int] = mapped_column(Money, default=0)
    variance_value: Mapped[int] = mapped_column(Money, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    #: Bucket breakdown + trend, precomputed so the dashboard is one row read.
    metrics: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    ai_status: Mapped[str] = mapped_column(String(24), default=AiStatus.PENDING.value)
    ai_analysed_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_report: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    transactions: Mapped[list["TransactionResult"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="noload"
    )


class TransactionResult(Base):
    """One reconciled record.  The largest table -- keep it narrow and indexed."""

    __tablename__ = "transaction_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_jobs.id"), index=True)

    order_id: Mapped[str] = mapped_column(String(128))
    payment_id: Mapped[str] = mapped_column(String(128))
    settlement_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    expected_amount: Mapped[int] = mapped_column(Money, default=0)
    settled_amount: Mapped[int] = mapped_column(Money, default=0)
    difference: Mapped[int] = mapped_column(Money, default=0)
    fee: Mapped[int] = mapped_column(Money, default=0)
    tax: Mapped[int] = mapped_column(Money, default=0)
    refund: Mapped[int] = mapped_column(Money, default=0)
    adjustment: Mapped[int] = mapped_column(Money, default=0)
    accounted_for: Mapped[int] = mapped_column(Money, default=0)
    unexplained: Mapped[int] = mapped_column(Money, default=0)

    status: Mapped[str] = mapped_column(String(24))
    exception_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cause: Mapped[str | None] = mapped_column(String(48), nullable=True)
    confidence: Mapped[str] = mapped_column(String(12), default="high")
    reason: Mapped[str] = mapped_column(Text, default="")

    currency: Mapped[str] = mapped_column(String(8), default="INR")
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    order_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    settlement_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    job: Mapped[ReconciliationJob] = relationship(back_populates="transactions")

    __table_args__ = (
        # The exact shapes the transactions endpoint filters on.
        Index("ix_txn_job_status", "job_id", "status"),
        Index("ix_txn_job_type", "job_id", "exception_type"),
        Index("ix_txn_job_order", "job_id", "order_id"),
        Index("ix_txn_job_date", "job_id", "settlement_date"),
    )


class ExceptionRecord(Base):
    """An exception plus its evidence and (advisory) AI analysis.

    Kept separate from ``transaction_results`` because it is one or two orders
    of magnitude smaller and carries wide JSON payloads.  Putting the evidence
    blob on the main table would bloat every transaction-page scan.
    """

    __tablename__ = "exception_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True,
                                    default=lambda: new_id("exc"))
    job_id: Mapped[str] = mapped_column(ForeignKey("reconciliation_jobs.id"), index=True)

    order_id: Mapped[str] = mapped_column(String(128))
    payment_id: Mapped[str] = mapped_column(String(128))
    settlement_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    expected_amount: Mapped[int] = mapped_column(Money, default=0)
    actual_amount: Mapped[int] = mapped_column(Money, default=0)
    difference: Mapped[int] = mapped_column(Money, default=0)
    fee: Mapped[int] = mapped_column(Money, default=0)
    tax: Mapped[int] = mapped_column(Money, default=0)
    refund: Mapped[int] = mapped_column(Money, default=0)
    adjustment: Mapped[int] = mapped_column(Money, default=0)
    accounted_for: Mapped[int] = mapped_column(Money, default=0)
    unexplained: Mapped[int] = mapped_column(Money, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")

    exception_type: Mapped[str] = mapped_column(String(32), index=True)
    cause: Mapped[str | None] = mapped_column(String(48), nullable=True)
    #: Deterministic confidence in the classification.
    confidence: Mapped[str] = mapped_column(String(12), default="high")
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")

    #: Source records cited, and the deterministic pass/fail check-list.
    evidence: Mapped[list[Any] | None] = mapped_column(nullable=True)
    checks: Mapped[list[Any] | None] = mapped_column(nullable=True)

    # -- advisory AI layer. Never feeds back into any figure above. --------
    ai_status: Mapped[str] = mapped_column(String(24), default=AiStatus.PENDING.value)
    ai_classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[str | None] = mapped_column(String(12), nullable=True)
    ai_signals: Mapped[list[Any] | None] = mapped_column(nullable=True)
    ai_recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(96), nullable=True)
    ai_tokens: Mapped[int] = mapped_column(Integer, default=0)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_analysed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_exc_job_type", "job_id", "exception_type"),
        Index("ix_exc_job_order", "job_id", "order_id"),
    )


class AuditEvent(Base):
    """Append-only.  Never updated, never deleted by application code."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    message: Mapped[str] = mapped_column(Text)
    #: Free-form pointer to whatever the event is about (order id, file name...).
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor: Mapped[str] = mapped_column(String(24), default="Engine")
    engine: Mapped[str] = mapped_column(String(16), default="deterministic")
    severity: Mapped[str] = mapped_column(String(12), default="ok")
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    __table_args__ = (Index("ix_audit_job_time", "job_id", "created_at"),)
