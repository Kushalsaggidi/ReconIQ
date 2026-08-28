"""Streaming metrics.

An accumulator, not a query.  It folds one outcome at a time and holds O(1)
memory regardless of dataset size -- which is what makes the engine chunkable:
metrics for 1M records cost exactly as much RAM as metrics for 100.

Every figure here is integer arithmetic in Python.  The LLM never sees these
numbers before they are final and never contributes to them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import (
    AUTO_EXPLAINED_BUCKETS,
    BUCKET_ORDER,
    EXCEPTION_LABELS,
    ExceptionCause,
    ExceptionType,
    TxnStatus,
)
from app.schemas.domain import ReconOutcome


@dataclass
class MetricsAccumulator:
    total_records: int = 0
    matched_records: int = 0
    exception_records: int = 0
    unresolved_records: int = 0

    gross_value: int = 0
    settled_value: int = 0
    variance_value: int = 0
    unexplained_value: int = 0

    fee_total: int = 0
    tax_total: int = 0
    refund_total: int = 0

    bucket_counts: dict[str, int] = field(default_factory=dict)
    bucket_amounts: dict[str, int] = field(default_factory=dict)
    cause_counts: dict[str, int] = field(default_factory=dict)

    #: settlement day (ISO date) -> counters, for the trend chart.
    daily: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, outcome: ReconOutcome) -> None:
        self.total_records += 1
        self.gross_value += outcome.expected_amount
        self.settled_value += outcome.settled_amount
        self.variance_value += outcome.difference
        self.unexplained_value += outcome.unexplained
        self.fee_total += outcome.fee
        self.tax_total += outcome.tax
        self.refund_total += outcome.refund

        if outcome.status is TxnStatus.MATCHED:
            self.matched_records += 1
        elif outcome.status is TxnStatus.UNRESOLVED:
            self.unresolved_records += 1
        else:
            self.exception_records += 1

        if outcome.exception_type is not None:
            key = outcome.exception_type.value
            self.bucket_counts[key] = self.bucket_counts.get(key, 0) + 1
            self.bucket_amounts[key] = self.bucket_amounts.get(key, 0) + abs(outcome.unexplained)
        if outcome.cause is not None:
            ck = outcome.cause.value
            self.cause_counts[ck] = self.cause_counts.get(ck, 0) + 1

        day = outcome.settlement_day
        if day is not None:
            slot = self.daily.setdefault(
                day.isoformat(), {"processed": 0, "matched": 0, "exceptions": 0}
            )
            slot["processed"] += 1
            if outcome.status is TxnStatus.MATCHED:
                slot["matched"] += 1
            else:
                slot["exceptions"] += 1

    def merge(self, other: "MetricsAccumulator") -> None:
        """Fold another accumulator in -- the hook for parallel workers later."""
        self.total_records += other.total_records
        self.matched_records += other.matched_records
        self.exception_records += other.exception_records
        self.unresolved_records += other.unresolved_records
        self.gross_value += other.gross_value
        self.settled_value += other.settled_value
        self.variance_value += other.variance_value
        self.unexplained_value += other.unexplained_value
        self.fee_total += other.fee_total
        self.tax_total += other.tax_total
        self.refund_total += other.refund_total
        for key, value in other.bucket_counts.items():
            self.bucket_counts[key] = self.bucket_counts.get(key, 0) + value
        for key, value in other.bucket_amounts.items():
            self.bucket_amounts[key] = self.bucket_amounts.get(key, 0) + value
        for key, value in other.cause_counts.items():
            self.cause_counts[key] = self.cause_counts.get(key, 0) + value
        for day, slot in other.daily.items():
            target = self.daily.setdefault(
                day, {"processed": 0, "matched": 0, "exceptions": 0}
            )
            for k, v in slot.items():
                target[k] += v

    # -- derived ---------------------------------------------------------

    @property
    def match_rate(self) -> float:
        if not self.total_records:
            return 0.0
        return round(self.matched_records / self.total_records * 100, 2)

    def buckets(self) -> list[dict[str, Any]]:
        """Exception breakdown in the UI's display order, zeros included.

        Zero-count buckets are kept so the chart does not reflow between runs.
        """
        return [
            {
                "type": b.value,
                "label": EXCEPTION_LABELS[b],
                "count": self.bucket_counts.get(b.value, 0),
                "amount": self.bucket_amounts.get(b.value, 0),
                "autoExplained": b in AUTO_EXPLAINED_BUCKETS,
            }
            for b in BUCKET_ORDER
        ]

    def breakdown(self) -> dict[str, int]:
        """Flat counters, named as the spec asks for them."""
        get = self.bucket_counts.get
        return {
            "partial_payment_count": get(ExceptionType.PARTIAL_PAYMENT.value, 0),
            "refund_count": get(ExceptionType.REFUND.value, 0),
            "fee_tax_count": get(ExceptionType.FEE_TAX.value, 0),
            "rounding_count": get(ExceptionType.ROUNDING.value, 0),
            "unresolved_count": get(ExceptionType.UNRESOLVED.value, 0),
        }

    def trend(self) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for day in sorted(self.daily):
            slot = self.daily[day]
            processed = slot["processed"] or 1
            points.append(
                {
                    "date": day,
                    "label": day[5:],
                    "processed": slot["processed"],
                    "matched": slot["matched"],
                    "exceptions": slot["exceptions"],
                    "matchRate": round(slot["matched"] / processed * 100, 2),
                }
            )
        return points

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "matched_records": self.matched_records,
            "exception_records": self.exception_records,
            "unresolved_records": self.unresolved_records,
            "match_rate": self.match_rate,
            "gross_value": self.gross_value,
            "settled_value": self.settled_value,
            "variance_value": self.variance_value,
            "unexplained_value": self.unexplained_value,
            "fee_total": self.fee_total,
            "tax_total": self.tax_total,
            "refund_total": self.refund_total,
            "buckets": self.buckets(),
            "breakdown": self.breakdown(),
            "cause_counts": dict(self.cause_counts),
            "trend": self.trend(),
        }


#: Causes that mean "a source record was missing", surfaced separately in the
#: summary so the UI can say *why* something is unresolved.
STRUCTURAL_CAUSES = frozenset(
    {
        ExceptionCause.MISSING_SETTLEMENT,
        ExceptionCause.MISSING_BANK_CREDIT,
        ExceptionCause.ORPHAN_SETTLEMENT,
        ExceptionCause.DUPLICATE_SETTLEMENT,
    }
)
