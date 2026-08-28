"""Canonical, in-memory record shapes.

These are the *only* things the reconciliation engine knows about.  Ingestion's
job is to turn any vaguely-shaped CSV into these; the engine's job is to
reconcile them.  Neither knows about HTTP, SQL or pandas.

They are ``slots=True`` dataclasses rather than Pydantic models on purpose:
this is the hot path, and at 1M records the attribute-dict overhead and
per-instance validation cost of Pydantic is the difference between a job that
finishes and one that doesn't.  Validation already happened at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.core.enums import Confidence, ExceptionCause, ExceptionType, TxnStatus


@dataclass(slots=True)
class OrderRecord:
    order_id: str
    payment_id: str
    #: Gross order value in minor units.
    order_amount: int
    currency: str = "INR"
    order_date: datetime | None = None
    status: str | None = None
    method: str | None = None
    source_row: int | None = None


@dataclass(slots=True)
class SettlementRecord:
    settlement_id: str
    payment_id: str
    #: Amount Razorpay says it settled (net), in minor units.
    settlement_amount: int
    #: Gross captured amount before deductions. Falls back to the order amount
    #: when the settlement file does not carry it.
    gross_amount: int | None = None
    fee: int = 0
    tax: int = 0
    refund_amount: int = 0
    adjustment: int = 0
    currency: str = "INR"
    settlement_date: datetime | None = None
    utr: str | None = None
    status: str | None = None
    source_row: int | None = None


@dataclass(slots=True)
class BankRecord:
    bank_transaction_id: str
    #: May be absent -- some statements only carry the UTR.
    settlement_id: str | None
    utr: str | None
    credit_amount: int
    currency: str = "INR"
    transaction_date: datetime | None = None
    description: str | None = None
    source_row: int | None = None


@dataclass(slots=True)
class ExceptionEvidenceItem:
    """One source record cited as evidence, plus the fields that matter."""

    source: str
    record_id: str | None
    present: bool
    fields: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "recordId": self.record_id,
            "present": self.present,
            "fields": [{"label": k, "value": v} for k, v in self.fields],
        }


@dataclass(slots=True)
class DeterministicCheck:
    label: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "passed": self.passed, "detail": self.detail}


@dataclass(slots=True)
class ReconOutcome:
    """The complete deterministic verdict on one order.

    Every monetary field is an ``int`` of minor units, and every one of them was
    produced by Python arithmetic.  The AI layer may read this object; it may
    never write to it.
    """

    order_id: str
    payment_id: str
    settlement_id: str | None
    bank_reference: str | None

    #: Gross order value -- what the merchant sold.
    expected_amount: int
    #: What actually landed (bank credit if traced, else settlement net).
    settled_amount: int
    #: expected - settled.
    difference: int

    fee: int
    tax: int
    refund: int
    adjustment: int

    #: Sum of declared components that legitimately explain part of the gap.
    accounted_for: int
    #: difference - accounted_for. This is what the status is decided on.
    unexplained: int

    status: TxnStatus
    exception_type: ExceptionType | None
    cause: ExceptionCause | None
    #: Deterministic confidence in the *classification* (not the arithmetic).
    confidence: Confidence
    reason: str

    currency: str = "INR"
    order_date: datetime | None = None
    settlement_date: datetime | None = None
    method: str | None = None
    checks: list[DeterministicCheck] = field(default_factory=list)
    evidence: list[ExceptionEvidenceItem] = field(default_factory=list)

    @property
    def is_exception(self) -> bool:
        return self.status is not TxnStatus.MATCHED

    @property
    def settlement_day(self) -> date | None:
        d = self.settlement_date or self.order_date
        return d.date() if d else None


@dataclass(slots=True)
class NormalizedDataset:
    """Result of ingesting one file: canonical records + a validation report."""

    kind: str
    records: list[Any]
    row_count: int
    rejected_count: int
    column_mapping: dict[str, str]
    issues: dict[str, Any]
    checksum: str | None = None
    source_name: str | None = None
