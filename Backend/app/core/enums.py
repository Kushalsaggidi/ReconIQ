"""Shared vocabulary.

The string *values* of these enums are part of the public API contract and are
consumed verbatim by the frontend -- do not rename them casually.
"""

from __future__ import annotations

from enum import Enum


class DatasetKind(str, Enum):
    ORDERS = "orders"
    SETTLEMENTS = "settlements"
    BANK = "bank"


class TxnStatus(str, Enum):
    """Deterministic outcome for one reconciled record."""

    MATCHED = "matched"
    EXCEPTION = "exception"
    UNRESOLVED = "unresolved"


class ExceptionType(str, Enum):
    """Cause of the *unexplained* residual, assigned by deterministic rules.

    These are the buckets the UI groups by.  ``FEE_DEDUCTION`` and
    ``TAX_DEDUCTION`` are tracked separately internally (see
    :class:`ExceptionCause`) but roll up to ``fee_tax`` for display.
    """

    PARTIAL_PAYMENT = "partial_payment"
    REFUND = "refund"
    FEE_TAX = "fee_tax"
    ROUNDING = "rounding"
    UNRESOLVED = "unresolved"


class ExceptionCause(str, Enum):
    """The finer-grained deterministic cause, stored for audit and evidence."""

    FEE_DEDUCTION = "FEE_DEDUCTION"
    TAX_DEDUCTION = "TAX_DEDUCTION"
    REFUND = "REFUND"
    PARTIAL_PAYMENT = "PARTIAL_PAYMENT"
    ROUNDING_DIFFERENCE = "ROUNDING_DIFFERENCE"
    OVER_SETTLEMENT = "OVER_SETTLEMENT"
    MISSING_SETTLEMENT = "MISSING_SETTLEMENT"
    MISSING_BANK_CREDIT = "MISSING_BANK_CREDIT"
    ORPHAN_SETTLEMENT = "ORPHAN_SETTLEMENT"
    DUPLICATE_SETTLEMENT = "DUPLICATE_SETTLEMENT"
    UNRESOLVED = "UNRESOLVED"

    @property
    def bucket(self) -> ExceptionType:
        return _CAUSE_TO_BUCKET[self]


_CAUSE_TO_BUCKET: dict[ExceptionCause, ExceptionType] = {
    ExceptionCause.FEE_DEDUCTION: ExceptionType.FEE_TAX,
    ExceptionCause.TAX_DEDUCTION: ExceptionType.FEE_TAX,
    ExceptionCause.REFUND: ExceptionType.REFUND,
    ExceptionCause.PARTIAL_PAYMENT: ExceptionType.PARTIAL_PAYMENT,
    ExceptionCause.ROUNDING_DIFFERENCE: ExceptionType.ROUNDING,
    ExceptionCause.OVER_SETTLEMENT: ExceptionType.PARTIAL_PAYMENT,
    ExceptionCause.MISSING_SETTLEMENT: ExceptionType.UNRESOLVED,
    ExceptionCause.MISSING_BANK_CREDIT: ExceptionType.UNRESOLVED,
    ExceptionCause.ORPHAN_SETTLEMENT: ExceptionType.UNRESOLVED,
    ExceptionCause.DUPLICATE_SETTLEMENT: ExceptionType.UNRESOLVED,
    ExceptionCause.UNRESOLVED: ExceptionType.UNRESOLVED,
}

#: Buckets the deterministic engine can fully account for. Drives the
#: `autoExplained` flag the UI uses to colour the breakdown chart.
AUTO_EXPLAINED_BUCKETS: frozenset[ExceptionType] = frozenset(
    {ExceptionType.FEE_TAX, ExceptionType.REFUND, ExceptionType.ROUNDING}
)

EXCEPTION_LABELS: dict[ExceptionType, str] = {
    ExceptionType.PARTIAL_PAYMENT: "Partial payment",
    ExceptionType.REFUND: "Refund",
    ExceptionType.FEE_TAX: "Fee / tax",
    ExceptionType.ROUNDING: "Rounding",
    ExceptionType.UNRESOLVED: "Unresolved",
}

#: Display order used by the exception-breakdown chart.
BUCKET_ORDER: tuple[ExceptionType, ...] = (
    ExceptionType.PARTIAL_PAYMENT,
    ExceptionType.REFUND,
    ExceptionType.FEE_TAX,
    ExceptionType.ROUNDING,
    ExceptionType.UNRESOLVED,
)


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStage(str, Enum):
    VALIDATE = "validate"
    NORMALIZE = "normalize"
    MATCH = "match"
    DETECT = "detect"
    AI = "ai"
    FINALIZE = "finalize"


class AiStatus(str, Enum):
    """Whether the advisory AI layer produced a result for an exception."""

    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class AuditEventType(str, Enum):
    DATASET_UPLOADED = "DATASET_UPLOADED"
    DATASET_VALIDATED = "DATASET_VALIDATED"
    DATASET_NORMALIZED = "DATASET_NORMALIZED"
    DATASET_REJECTED = "DATASET_REJECTED"
    RECONCILIATION_STARTED = "RECONCILIATION_STARTED"
    BATCH_PROCESSED = "BATCH_PROCESSED"
    RECORD_MATCHED = "RECORD_MATCHED"
    EXCEPTION_DETECTED = "EXCEPTION_DETECTED"
    AI_ANALYSIS_STARTED = "AI_ANALYSIS_STARTED"
    AI_ANALYSIS_COMPLETED = "AI_ANALYSIS_COMPLETED"
    AI_ANALYSIS_FAILED = "AI_ANALYSIS_FAILED"
    AI_ANALYSIS_SKIPPED = "AI_ANALYSIS_SKIPPED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
