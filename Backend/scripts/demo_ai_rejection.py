"""The wow moment, runnable in under a second, no API key required.

    python scripts/demo_ai_rejection.py

Runs a real reconciliation through the actual deterministic engine, takes the
real exception it produces, and shows the same ``AiVerdict.assert_grounded``
guard that ships in ``app/ai/schemas.py`` (exercised in
``tests/test_ai_layer.py``) doing its job live:

1. A grounded explanation -- every figure it cites came from the engine --
   is accepted.
2. A hallucinated explanation -- one invented number, otherwise identical --
   is rejected before it can reach a user or the database.

This does not call Gemini or any network. The point is not "the model didn't
hallucinate this time" -- it's that the *validation layer* rejects a
hallucination structurally, regardless of what any provider returns.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.schemas import AiVerdict, ExceptionFacts  # noqa: E402
from app.core.money import to_major  # noqa: E402
from app.reconciliation.engine import reconcile  # noqa: E402
from app.schemas.domain import BankRecord, OrderRecord, SettlementRecord  # noqa: E402

BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
DIM = "\033[2m"
RESET = "\033[0m"


def rupees(amount: float) -> int:
    return int(round(amount * 100))


def build_real_exception() -> ExceptionFacts:
    """Reconcile one real short-settlement case and return its exception facts."""
    order = OrderRecord(
        order_id="O-DEMO", payment_id="P-DEMO", order_amount=rupees(2000),
        currency="INR", order_date=datetime(2026, 8, 1, 10, 0, 0),
        status="captured", method="UPI",
    )
    settlement = SettlementRecord(
        settlement_id="S-DEMO", payment_id="P-DEMO", settlement_amount=rupees(1976.40),
        gross_amount=rupees(2000), fee=rupees(20), tax=rupees(3.60), refund_amount=0,
        currency="INR", settlement_date=datetime(2026, 8, 3, 12, 0, 0), utr="UTR-DEMO",
    )
    bank = BankRecord(
        bank_transaction_id="B-DEMO", settlement_id="S-DEMO", utr="UTR-DEMO",
        credit_amount=rupees(1976.40) - rupees(250),  # bank paid 250 less than settled
        currency="INR", transaction_date=datetime(2026, 8, 3, 12, 0, 0),
        description="NEFT CR RAZORPAY",
    )

    result = reconcile([order], [settlement], [bank])
    outcome = next(o for o in result.outcomes if o.is_exception)
    cur = outcome.currency
    return ExceptionFacts(
        exception_id="exc_demo",
        order_id=outcome.order_id,
        payment_id=outcome.payment_id,
        settlement_id=outcome.settlement_id,
        currency=cur,
        expected_amount=float(to_major(outcome.expected_amount, cur)),
        actual_amount=float(to_major(outcome.settled_amount, cur)),
        difference=float(to_major(outcome.difference, cur)),
        fee=float(to_major(outcome.fee, cur)),
        tax=float(to_major(outcome.tax, cur)),
        refund=float(to_major(outcome.refund, cur)),
        adjustment=float(to_major(outcome.adjustment, cur)),
        accounted_for=float(to_major(outcome.accounted_for, cur)),
        unexplained=float(to_major(outcome.unexplained, cur)),
        deterministic_type=outcome.exception_type.value if outcome.exception_type else "unresolved",
        deterministic_cause=outcome.cause.value if outcome.cause else None,
        deterministic_reason=outcome.reason,
    )


def rule(char: str = "-") -> None:
    print(char * 72)


def main() -> None:
    import logging

    logging.getLogger("app.reconciliation.engine").setLevel(logging.WARNING)
    facts = build_real_exception()

    print(f"\n{BOLD}PayRecon -- financial truth vs. AI explanation{RESET}\n")
    rule("=")
    print(f"{BOLD}1. Deterministic engine output (no AI involved){RESET}")
    print(f"   Order {facts.order_id} / Payment {facts.payment_id}")
    print(f"   Expected      : {facts.expected_amount:,.2f} {facts.currency}")
    print(f"   Actually paid : {facts.actual_amount:,.2f} {facts.currency}")
    print(f"   Unexplained   : {facts.unexplained:,.2f} {facts.currency}  <- this is the only number that is real")
    rule()

    print(f"\n{BOLD}2. AI explanation grounded in the real figures -> accepted{RESET}")
    good = AiVerdict(
        exception_id=facts.exception_id,
        classification=facts.deterministic_type,
        explanation=(
            f"The bank credited {facts.actual_amount:,.2f} against an expected "
            f"{facts.expected_amount:,.2f}, leaving {facts.unexplained:,.2f} unexplained."
        ),
    )
    good.assert_grounded(facts)
    print(f'   "{good.explanation}"')
    print(f"   {GREEN}{BOLD}ACCEPTED{RESET} -- every number in that sentence came from the facts payload above.")
    rule()

    print(f"\n{BOLD}3. AI explanation citing a plausible but invented figure -> rejected{RESET}")
    invented_figure = f"{facts.unexplained + 173.45:,.2f}"
    hallucinated = AiVerdict(
        exception_id=facts.exception_id,
        classification=facts.deterministic_type,
        explanation=(
            f"A processing adjustment of {invented_figure} explains the shortfall "
            f"between expected and settled amounts."
        ),
    )
    print(f'   "{hallucinated.explanation}"')
    try:
        hallucinated.assert_grounded(facts)
        print(f"   {RED}{BOLD}THIS SHOULD NOT PRINT -- grounding guard failed to catch it{RESET}")
        sys.exit(1)
    except ValueError as exc:
        print(f"   {RED}{BOLD}REJECTED{RESET} -- {exc}")
    rule("=")
    print(
        f"\n{DIM}This is app/ai/schemas.py::AiVerdict.assert_grounded, the same guard every\n"
        f"provider (Gemini, Anthropic, OpenAI) calls before a verdict is stored.\n"
        f"Unit-tested in tests/test_ai_layer.py::test_explanation_citing_an_invented_figure_is_rejected.\n"
        f"No AI can control this number -- the validation layer isn't asking it to behave,\n"
        f"it's checking its work.{RESET}\n"
    )


if __name__ == "__main__":
    main()
