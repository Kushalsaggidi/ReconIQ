"""The seven reconciliation scenarios, one test each.

These are the specification.  If a rule changes, one of these must change with
it -- which is the point: the business rules are pinned by executable examples
rather than by prose.
"""

from __future__ import annotations

import pytest

from app.core.enums import ExceptionCause, ExceptionType, TxnStatus
from app.reconciliation.config import ReconciliationConfig
from app.reconciliation.engine import ReconciliationEngine, reconcile
from tests.conftest import (
    FEE,
    GROSS,
    NET,
    TAX,
    make_bank,
    make_order,
    make_settlement,
    rupees,
)


def run_one(order, settlement, bank, config=None):
    """Reconcile a single chain and return its outcome."""
    result = reconcile(
        [order],
        [settlement] if settlement else [],
        [bank] if bank else [],
        config,
    )
    # Filter out any orphan rows so the assertions target the order itself.
    return next(o for o in result.outcomes if o.order_id == order.order_id)


# 1 -------------------------------------------------------------------------

def test_perfect_match_is_matched():
    """Declared fee and tax fully explain the gap -> MATCHED, not an exception."""
    outcome = run_one(make_order(), make_settlement(), make_bank())

    assert outcome.status is TxnStatus.MATCHED
    assert outcome.exception_type is None
    assert outcome.expected_amount == GROSS
    assert outcome.settled_amount == NET
    assert outcome.difference == FEE + TAX
    assert outcome.accounted_for == FEE + TAX
    assert outcome.unexplained == 0


def test_matched_with_no_deductions_at_all():
    settlement = make_settlement(net=GROSS, fee=0, tax=0)
    outcome = run_one(make_order(), settlement, make_bank(credit=GROSS))

    assert outcome.status is TxnStatus.MATCHED
    assert outcome.difference == 0
    assert outcome.unexplained == 0


# 2 + 3 ---------------------------------------------------------------------

def test_fee_deducted_twice_is_a_fee_tax_exception():
    """Bank credit is short by exactly the declared fee + tax."""
    outcome = run_one(
        make_order(), make_settlement(), make_bank(credit=NET - (FEE + TAX))
    )

    assert outcome.status is TxnStatus.EXCEPTION
    assert outcome.exception_type is ExceptionType.FEE_TAX
    assert outcome.cause is ExceptionCause.FEE_DEDUCTION
    assert outcome.unexplained == FEE + TAX


def test_tax_deducted_twice_is_a_tax_exception():
    outcome = run_one(make_order(), make_settlement(), make_bank(credit=NET - TAX))

    assert outcome.exception_type is ExceptionType.FEE_TAX
    assert outcome.cause is ExceptionCause.TAX_DEDUCTION
    assert outcome.unexplained == TAX


# 4 -------------------------------------------------------------------------

def test_refund_applied_twice_is_a_refund_exception():
    refund = rupees(500)
    settlement = make_settlement(net=NET - refund, refund=refund)
    outcome = run_one(make_order(), settlement, make_bank(credit=NET - refund * 2))

    assert outcome.status is TxnStatus.EXCEPTION
    assert outcome.exception_type is ExceptionType.REFUND
    assert outcome.refund == refund
    assert outcome.unexplained == refund


# 5 -------------------------------------------------------------------------

def test_partial_payment():
    """A shortfall no declared component explains."""
    shortfall = rupees(250)
    outcome = run_one(make_order(), make_settlement(), make_bank(credit=NET - shortfall))

    assert outcome.status is TxnStatus.EXCEPTION
    assert outcome.exception_type is ExceptionType.PARTIAL_PAYMENT
    assert outcome.unexplained == shortfall
    assert "short" in outcome.reason.lower()


def test_over_settlement_is_flagged_not_ignored():
    outcome = run_one(make_order(), make_settlement(), make_bank(credit=NET + rupees(300)))

    assert outcome.status is TxnStatus.EXCEPTION
    assert outcome.cause is ExceptionCause.OVER_SETTLEMENT
    assert outcome.unexplained == -rupees(300)


# 6 -------------------------------------------------------------------------

@pytest.mark.parametrize("residual", [1, 25, 99, 100])
def test_sub_tolerance_residual_is_rounding(residual: int):
    outcome = run_one(make_order(), make_settlement(), make_bank(credit=NET - residual))

    assert outcome.exception_type is ExceptionType.ROUNDING
    assert outcome.unexplained == residual


def test_just_above_tolerance_is_not_rounding():
    """101 paise is a real variance; the boundary must not be fuzzy."""
    outcome = run_one(make_order(), make_settlement(), make_bank(credit=NET - 101))

    assert outcome.exception_type is ExceptionType.PARTIAL_PAYMENT


def test_rounding_tolerance_is_configurable():
    config = ReconciliationConfig(rounding_tolerance_minor=500)
    outcome = run_one(
        make_order(), make_settlement(), make_bank(credit=NET - 400), config
    )

    assert outcome.exception_type is ExceptionType.ROUNDING


# 7 -------------------------------------------------------------------------

def test_missing_settlement_is_unresolved_and_explains_nothing():
    outcome = run_one(make_order(), None, None)

    assert outcome.status is TxnStatus.UNRESOLVED
    assert outcome.cause is ExceptionCause.MISSING_SETTLEMENT
    assert outcome.settlement_id is None
    # Critically: the engine must not invent a cause for the whole gross value.
    assert outcome.unexplained == GROSS
    assert "no settlement record" in outcome.reason.lower()


def test_duplicate_settlement_refuses_to_guess():
    """Split payout or duplicated export? The engine must not choose."""
    result = reconcile(
        [make_order()],
        [make_settlement("S-1"), make_settlement("S-2", utr="UTR-2")],
        [make_bank()],
    )
    outcome = result.outcomes[0]

    assert outcome.status is TxnStatus.UNRESOLVED
    assert outcome.cause is ExceptionCause.DUPLICATE_SETTLEMENT
    assert outcome.exception_type is ExceptionType.UNRESOLVED


def test_orphan_settlement_is_surfaced_not_dropped():
    """Money moved with no order behind it is a finding, not a non-event."""
    result = reconcile(
        [make_order("O-1", "P-1")],
        [make_settlement("S-1", "P-1"), make_settlement("S-9", "P-9", utr="UTR-9")],
        [make_bank()],
    )

    orphans = [o for o in result.outcomes if o.cause is ExceptionCause.ORPHAN_SETTLEMENT]
    assert len(orphans) == 1
    assert orphans[0].status is TxnStatus.UNRESOLVED
    assert orphans[0].settlement_id == "S-9"
    assert result.metrics.total_records == 2


# Matching behaviour ---------------------------------------------------------

def test_bank_matched_by_utr_when_settlement_id_absent():
    bank = make_bank(settlement_id=None, utr="UTR-1")
    outcome = run_one(make_order(), make_settlement(), bank)

    assert outcome.status is TxnStatus.MATCHED
    assert outcome.bank_reference == "UTR-1"


def test_settlement_net_used_when_no_bank_leg():
    outcome = run_one(make_order(), make_settlement(), None)

    assert outcome.status is TxnStatus.MATCHED
    assert outcome.settled_amount == NET
    assert outcome.bank_reference is None


def test_strict_mode_requires_a_bank_leg():
    config = ReconciliationConfig(allow_settlement_as_actual=False)
    outcome = run_one(make_order(), make_settlement(), None, config)

    assert outcome.status is TxnStatus.UNRESOLVED
    assert outcome.cause is ExceptionCause.MISSING_BANK_CREDIT


def test_evidence_and_checks_are_attached_to_every_outcome():
    outcome = run_one(make_order(), make_settlement(), make_bank(credit=NET - rupees(250)))

    sources = {e.source for e in outcome.evidence}
    assert sources == {"Orders dataset", "Razorpay settlement", "Bank statement"}
    assert all(e.present for e in outcome.evidence)

    variance_check = next(c for c in outcome.checks if c.label == "Variance fully accounted for")
    assert variance_check.passed is False


def test_no_evidence_is_marked_absent_rather_than_fabricated():
    outcome = run_one(make_order(), None, None)

    bank_evidence = next(e for e in outcome.evidence if e.source == "Bank statement")
    settlement_evidence = next(e for e in outcome.evidence if e.source == "Razorpay settlement")
    assert bank_evidence.present is False
    assert bank_evidence.fields == []
    assert settlement_evidence.present is False


# Batching -------------------------------------------------------------------

def test_batching_does_not_change_results():
    """The chunk size is a performance knob, never a correctness one."""
    orders = [make_order(f"O-{i}", f"P-{i}") for i in range(250)]
    settlements = [make_settlement(f"S-{i}", f"P-{i}", utr=f"U-{i}") for i in range(250)]
    banks = [make_bank(f"B-{i}", f"S-{i}", utr=f"U-{i}") for i in range(250)]

    whole = ReconciliationEngine(ReconciliationConfig(batch_size=10_000)).run(
        orders, settlements, banks
    )
    chunked = ReconciliationEngine(ReconciliationConfig(batch_size=7)).run(
        orders, settlements, banks
    )

    assert chunked.batches > 30
    assert whole.metrics.to_dict() == chunked.metrics.to_dict()
    assert [o.order_id for o in whole.outcomes] == [o.order_id for o in chunked.outcomes]


def test_on_batch_sink_receives_every_record_without_collecting():
    orders = [make_order(f"O-{i}", f"P-{i}") for i in range(50)]
    seen: list[str] = []

    result = ReconciliationEngine(ReconciliationConfig(batch_size=8)).run(
        orders, [], [], collect_outcomes=False, on_batch=lambda b: seen.extend(o.order_id for o in b)
    )

    assert result.outcomes == []          # nothing retained in memory
    assert len(seen) == 50                # everything still delivered
    assert result.metrics.total_records == 50
