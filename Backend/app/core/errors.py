"""Error taxonomy.

Three severities, used consistently from ingestion through to the API:

``WARNING``    the record survives, but something was coerced or assumed.
``EXCEPTION``  a business-level variance -- expected in a reconciliation run.
``ERROR``      the record or the file could not be processed at all.

Nothing is ever silently dropped.  A rejected row becomes a ``RecordIssue``
carrying the dataset, row number, column and the raw value, so an operator can
open the CSV and look at the exact cell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    WARNING = "WARNING"
    EXCEPTION = "EXCEPTION"
    ERROR = "ERROR"


class ErrorCode(str, Enum):
    # File level
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
    EMPTY_FILE = "EMPTY_FILE"
    UNREADABLE_FILE = "UNREADABLE_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    MISSING_REQUIRED_COLUMNS = "MISSING_REQUIRED_COLUMNS"
    AMBIGUOUS_COLUMN = "AMBIGUOUS_COLUMN"

    # Row level
    MISSING_IDENTIFIER = "MISSING_IDENTIFIER"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_DATE = "INVALID_DATE"
    DUPLICATE_IDENTIFIER = "DUPLICATE_IDENTIFIER"
    UNSUPPORTED_CURRENCY = "UNSUPPORTED_CURRENCY"
    NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"

    # Job level
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    RECONCILIATION_FAILED = "RECONCILIATION_FAILED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"


@dataclass(slots=True)
class RecordIssue:
    """A single, addressable problem with one row (or one file)."""

    code: ErrorCode
    severity: Severity
    message: str
    dataset: str | None = None
    row_number: int | None = None
    column: str | None = None
    raw_value: Any = None
    record_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "dataset": self.dataset,
            "rowNumber": self.row_number,
            "column": self.column,
            "rawValue": None if self.raw_value is None else str(self.raw_value)[:120],
            "recordId": self.record_id,
        }


class ReconError(Exception):
    """Base class for every error this application raises deliberately."""

    status_code: int = 400
    code: ErrorCode = ErrorCode.RECONCILIATION_FAILED

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        status_code: int | None = None,
        issues: list[RecordIssue] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.issues = issues or []
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "context": self.context,
                "issues": [i.to_dict() for i in self.issues],
            }
        }


class ValidationFailure(ReconError):
    status_code = 422
    code = ErrorCode.MISSING_REQUIRED_COLUMNS


class IngestionError(ReconError):
    status_code = 400
    code = ErrorCode.UNREADABLE_FILE


class NotFoundError(ReconError):
    status_code = 404
    code = ErrorCode.JOB_NOT_FOUND


class ReconciliationFailure(ReconError):
    status_code = 500
    code = ErrorCode.RECONCILIATION_FAILED


class LLMUnavailable(ReconError):
    """Raised inside the AI layer only.  Never propagates to a job failure."""

    status_code = 503
    code = ErrorCode.LLM_UNAVAILABLE


@dataclass
class IssueCollector:
    """Accumulates issues with a cap, so a pathological file cannot blow memory.

    ``total_*`` counters keep counting after the sample cap is reached, so the
    report still tells the truth about how many rows were affected.
    """

    max_samples: int = 200
    samples: list[RecordIssue] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, issue: RecordIssue) -> None:
        self.counts[issue.code.value] = self.counts.get(issue.code.value, 0) + 1
        if len(self.samples) < self.max_samples:
            self.samples.append(issue)

    def extend(self, issues: list[RecordIssue]) -> None:
        for issue in issues:
            self.add(issue)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def count_of(self, severity: Severity) -> int:
        return sum(1 for s in self.samples if s.severity is severity)

    def has_errors(self) -> bool:
        return any(s.severity is Severity.ERROR for s in self.samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "byCode": self.counts,
            "samples": [s.to_dict() for s in self.samples],
            "truncated": self.total > len(self.samples),
        }
