"""Deterministic exception classification.

An ordered decision table.  Each rule is a pure function of already-computed
figures; the first one that fires wins.  No rule may invent a number, and any
residual that no rule can attribute to a source record falls through to
``UNRESOLVED`` -- which is a legitimate answer, not a failure.

This is deliberately readable top-to-bottom: an auditor should be able to point
at a record's status and find the exact line that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums import Confidence, ExceptionCause, TxnStatus
from app.core.money import format_money
from app.reconciliation.config import ReconciliationConfig
from app.reconciliation.matcher import MatchResult
from app.schemas.domain import DeterministicCheck


@dataclass(slots=True)
class Facts:
    """Everything the rules are allowed to look at.  All figures are minor units."""

    expected_amount: int      # gross order value
    settled_amount: int       # what actually landed
    difference: int           # expected - settled
    fee: int
    tax: int
    refund: int
    adjustment: int
    accounted_for: int        # fee + tax + refund - adjustment
    unexplained: int          # difference - accounted_for
    has_settlement: bool
    has_bank_credit: bool
    duplicate_settlements: bool
    currency: str = "INR"


@dataclass(slots=True)
class Verdict:
    status: TxnStatus
    cause: ExceptionCause | None
    confidence: Confidence
    reason: str


def _near(value: int, target: int, tolerance: int) -> bool:
    return target != 0 and abs(abs(value) - abs(target)) <= tolerance


def classify(facts: Facts, config: ReconciliationConfig) -> Verdict:
    """Assign a deterministic status and cause.  Order matters."""
    money = lambda v: format_money(v, facts.currency)  # noqa: E731 - local alias
    tol = config.rounding_tolerance_minor
    attr = config.attribution_tolerance_minor

    # 1. Structural gaps come first: without a source record there is nothing
    #    to reconcile against, and any "explanation" would be invented.
    if not facts.has_settlement:
        return Verdict(
            TxnStatus.UNRESOLVED,
            ExceptionCause.MISSING_SETTLEMENT,
            Confidence.HIGH,
            "No settlement record references this payment ID.",
        )
    if not facts.has_bank_credit and not config.allow_settlement_as_actual:
        return Verdict(
            TxnStatus.UNRESOLVED,
            ExceptionCause.MISSING_BANK_CREDIT,
            Confidence.HIGH,
            "Settled per Razorpay, but no matching credit found in the bank statement.",
        )

    # 2. A duplicated/split settlement makes every downstream figure ambiguous.
    if facts.duplicate_settlements:
        return Verdict(
            TxnStatus.UNRESOLVED,
            ExceptionCause.DUPLICATE_SETTLEMENT,
            Confidence.MEDIUM,
            "Multiple settlement rows reference this payment ID; totals are ambiguous.",
        )

    # 3. Fully accounted for: declared fee/tax/refund explain the whole gap.
    if facts.unexplained == 0:
        return Verdict(
            TxnStatus.MATCHED,
            None,
            Confidence.HIGH,
            "Settled amount equals gross less declared fee, tax and refunds."
            if facts.accounted_for
            else "Settled amount equals the order amount exactly.",
        )

    # 4. Sub-tolerance residual: a rounding artefact, not a real variance.
    if abs(facts.unexplained) <= tol:
        return Verdict(
            TxnStatus.EXCEPTION,
            ExceptionCause.ROUNDING_DIFFERENCE,
            Confidence.HIGH,
            f"{money(facts.unexplained)} residual, within the "
            f"{money(tol)} rounding tolerance.",
        )

    # 5. Residual attributable to a specific declared component. We only make
    #    this claim when the residual *equals* that component -- i.e. it was
    #    applied twice or not at all. Anything looser would be a guess.
    if _near(facts.unexplained, facts.refund, attr):
        return Verdict(
            TxnStatus.EXCEPTION,
            ExceptionCause.REFUND,
            Confidence.HIGH,
            f"Residual of {money(facts.unexplained)} equals the declared refund of "
            f"{money(facts.refund)}; the refund appears to have been applied twice "
            "or not at all.",
        )
    if _near(facts.unexplained, facts.fee + facts.tax, attr):
        return Verdict(
            TxnStatus.EXCEPTION,
            ExceptionCause.FEE_DEDUCTION,
            Confidence.HIGH,
            f"Residual of {money(facts.unexplained)} equals declared fee plus tax "
            f"({money(facts.fee + facts.tax)}).",
        )
    if _near(facts.unexplained, facts.fee, attr):
        return Verdict(
            TxnStatus.EXCEPTION,
            ExceptionCause.FEE_DEDUCTION,
            Confidence.HIGH,
            f"Residual of {money(facts.unexplained)} equals the declared platform fee.",
        )
    if _near(facts.unexplained, facts.tax, attr):
        return Verdict(
            TxnStatus.EXCEPTION,
            ExceptionCause.TAX_DEDUCTION,
            Confidence.HIGH,
            f"Residual of {money(facts.unexplained)} equals the declared tax on fee.",
        )

    # 6. Over-settlement: more money arrived than the order justifies.
    if facts.unexplained < 0:
        return Verdict(
            TxnStatus.EXCEPTION,
            ExceptionCause.OVER_SETTLEMENT,
            Confidence.MEDIUM,
            f"{money(-facts.unexplained)} more was credited than the order and its "
            "declared components account for.",
        )

    # 7. Short credit against a real settlement, with money genuinely received.
    if facts.settled_amount > 0:
        return Verdict(
            TxnStatus.EXCEPTION,
            ExceptionCause.PARTIAL_PAYMENT,
            Confidence.MEDIUM,
            f"{money(facts.unexplained)} short of the expected net settlement; "
            "no declared component accounts for the shortfall.",
        )

    # 8. Nothing arrived at all.
    return Verdict(
        TxnStatus.UNRESOLVED,
        ExceptionCause.UNRESOLVED,
        Confidence.LOW,
        f"A settlement exists but no value was credited; {money(facts.difference)} "
        "is unaccounted for.",
    )


def build_checks(facts: Facts, match: MatchResult, verdict: Verdict) -> list[DeterministicCheck]:
    """The check-list the UI renders next to an exception.

    Each entry is a plain boolean over facts the engine already established --
    this is the evidence the AI layer is later constrained to reason within.
    """
    settlement = match.settlement
    money = lambda v: format_money(v, facts.currency)  # noqa: E731

    return [
        DeterministicCheck(
            label="Settlement record present",
            passed=facts.has_settlement,
            detail=(
                f"Linked to {settlement.settlement_id}"
                if settlement
                else "No settlement row references this payment ID"
            ),
        ),
        DeterministicCheck(
            label="Bank credit traced",
            passed=facts.has_bank_credit,
            detail=(
                f"UTR {match.bank_reference} found in the bank statement"
                if facts.has_bank_credit
                else "No matching UTR or settlement ID in the bank statement"
            ),
        ),
        DeterministicCheck(
            label="Settlement amount agrees with bank credit",
            passed=(
                not facts.has_bank_credit
                or settlement is None
                or settlement.settlement_amount == match.bank_credit_total
            ),
            detail=(
                f"Razorpay net {money(settlement.settlement_amount)} vs bank credit "
                f"{money(match.bank_credit_total)}"
                if settlement and facts.has_bank_credit
                else "Not applicable -- no bank leg to compare"
            ),
        ),
        DeterministicCheck(
            label="Variance fully accounted for",
            passed=facts.unexplained == 0,
            detail=(
                "Fee, tax and refund components fully explain the variance"
                if facts.unexplained == 0
                else f"{money(facts.unexplained)} of the variance has no supporting record"
            ),
        ),
        DeterministicCheck(
            label="Single settlement per payment",
            passed=not facts.duplicate_settlements,
            detail=(
                "Exactly one settlement row references this payment"
                if not facts.duplicate_settlements
                else "Several settlement rows reference this payment"
            ),
        ),
    ]
