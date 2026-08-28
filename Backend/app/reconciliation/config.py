"""Reconciliation rules as data.

Every threshold and every term of the settlement equation lives here, so
changing the business rules means editing this file (or passing a different
config object) -- never editing the engine.

The equation itself:

    expected_net = gross - fee - tax - refund + adjustment

and, separately, the figure the UI reconciles against:

    difference    = expected_gross - settled_actual
    accounted_for = fee + tax + refund - adjustment
    unexplained   = difference - accounted_for

``unexplained`` is the only quantity that decides a record's status.  A
settlement whose declared fees fully explain the shortfall is MATCHED, not an
exception -- which is what a treasury team actually means by "reconciled".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.schemas.domain import SettlementRecord

#: Which side of the equation each declared component sits on.
ComponentSign = Literal["deduct", "add"]


@dataclass(frozen=True, slots=True)
class SettlementComponent:
    """One term of the settlement equation."""

    name: str
    attribute: str
    sign: ComponentSign
    label: str
    enabled: bool = True

    def value(self, settlement: SettlementRecord | None) -> int:
        if settlement is None or not self.enabled:
            return 0
        return int(getattr(settlement, self.attribute, 0) or 0)

    def signed(self, settlement: SettlementRecord | None) -> int:
        v = self.value(settlement)
        return v if self.sign == "deduct" else -v


#: The default Razorpay-shaped equation. Add a component here (e.g. a chargeback
#: reserve) and it flows through expected_net, accounted_for and the evidence
#: payload automatically.
DEFAULT_COMPONENTS: tuple[SettlementComponent, ...] = (
    SettlementComponent("fee", "fee", "deduct", "Platform fee"),
    SettlementComponent("tax", "tax", "deduct", "Tax on fee (GST)"),
    SettlementComponent("refund", "refund_amount", "deduct", "Refund"),
    SettlementComponent("adjustment", "adjustment", "add", "Other adjustments"),
)


@dataclass(frozen=True, slots=True)
class ReconciliationConfig:
    """Tunable inputs to the deterministic engine."""

    currency: str = "INR"

    #: |unexplained| at or below this is a rounding artefact, not a real gap.
    rounding_tolerance_minor: int = 100  # Rs 1.00

    #: A residual that lands within this distance of a declared component is
    #: attributed to that component (e.g. a fee that was double-charged).
    attribution_tolerance_minor: int = 100

    #: Below this, an unexplained residual on an otherwise-good record is not
    #: worth an operator's time; it still shows as a rounding exception.
    components: tuple[SettlementComponent, ...] = DEFAULT_COMPONENTS

    #: When the bank statement is absent entirely, fall back to the settlement's
    #: own net amount as "actual". Set False to force every record unresolved
    #: without a bank leg (stricter, three-way-only reconciliation).
    allow_settlement_as_actual: bool = True

    #: Match settlements to bank rows on UTR when settlement_id is unavailable.
    match_bank_on_utr: bool = True

    #: Cap on evidence field strings kept per exception (bounds payload size).
    max_evidence_fields: int = 12

    #: Progress/persistence batch size.
    batch_size: int = 10_000

    def deductions(self) -> tuple[SettlementComponent, ...]:
        return tuple(c for c in self.components if c.sign == "deduct" and c.enabled)

    def additions(self) -> tuple[SettlementComponent, ...]:
        return tuple(c for c in self.components if c.sign == "add" and c.enabled)

    def accounted_for(self, settlement: SettlementRecord | None) -> int:
        """Sum of declared components that legitimately explain a shortfall."""
        return sum(c.signed(settlement) for c in self.components)

    def expected_net(self, gross: int, settlement: SettlementRecord | None) -> int:
        """gross - deductions + additions."""
        return gross - self.accounted_for(settlement)


@dataclass
class ReconciliationOptions:
    """Per-run knobs that are not business rules (progress, limits, labels)."""

    job_id: str = ""
    emit_matched_audit_events: bool = False
    #: Hard cap on RECORD_MATCHED/EXCEPTION_DETECTED audit rows written per job.
    #: The audit trail must stay explanatory, not become a second copy of the
    #: result table.
    max_detail_audit_events: int = 200
    progress_callback: object | None = field(default=None, repr=False)
