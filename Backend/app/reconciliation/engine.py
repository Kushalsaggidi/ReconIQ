"""The reconciliation engine.

Pure Python.  No FastAPI, no SQLAlchemy, no LLM.  You can import this module in
a notebook, hand it three lists of records, and get a full result -- which is
exactly how the tests and the benchmark use it.

Shape of the computation, per order:

    gross      = settlement.gross_amount or order.order_amount
    settled    = bank credit total, else settlement.settlement_amount
    difference = gross - settled
    accounted  = fee + tax + refund - adjustment      (declared components)
    unexplained = difference - accounted              <- decides the status

``process_batch`` is the unit of work.  ``run`` is a thin loop over batches, so
moving to a worker pool or a database cursor means changing the loop, not the
arithmetic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Sequence

from app.core.enums import (
    Confidence,
    ExceptionCause,
    ExceptionType,
    TxnStatus,
)
from app.core.logging import get_logger
from app.core.money import format_money
from app.reconciliation.config import ReconciliationConfig, ReconciliationOptions
from app.reconciliation.matcher import MatchIndex, MatchResult, match_order
from app.reconciliation.metrics import MetricsAccumulator
from app.reconciliation.rules import Facts, build_checks, classify
from app.schemas.domain import (
    BankRecord,
    ExceptionEvidenceItem,
    OrderRecord,
    ReconOutcome,
    SettlementRecord,
)

logger = get_logger(__name__)

#: Called as ``progress(processed, total, matched, exceptions)`` after each batch.
ProgressFn = Callable[[int, int, int, int], None]


@dataclass
class ReconciliationResult:
    """Everything one run produced."""

    metrics: MetricsAccumulator
    outcomes: list[ReconOutcome] = field(default_factory=list)
    duration_ms: int = 0
    batches: int = 0
    orphan_settlements: int = 0
    orphan_bank_rows: int = 0

    @property
    def exceptions(self) -> list[ReconOutcome]:
        return [o for o in self.outcomes if o.is_exception]


class ReconciliationEngine:
    """Deterministic three-way reconciliation.

    Stateless with respect to a run: build one, call :meth:`run`, keep the
    result.  Safe to reuse across jobs.
    """

    def __init__(self, config: ReconciliationConfig | None = None) -> None:
        self.config = config or ReconciliationConfig()

    # -- public API ------------------------------------------------------

    def run(
        self,
        orders: Sequence[OrderRecord],
        settlements: Sequence[SettlementRecord],
        bank_rows: Sequence[BankRecord],
        *,
        options: ReconciliationOptions | None = None,
        progress: ProgressFn | None = None,
        collect_outcomes: bool = True,
        on_batch: Callable[[list[ReconOutcome]], None] | None = None,
    ) -> ReconciliationResult:
        """Reconcile three datasets.

        ``collect_outcomes=False`` plus an ``on_batch`` sink lets a caller stream
        results straight to the database and keep peak memory flat -- the path
        we take for large jobs.
        """
        started = time.perf_counter()
        options = options or ReconciliationOptions()
        index = MatchIndex.build(
            settlements, bank_rows, match_bank_on_utr=self.config.match_bank_on_utr
        )
        metrics = MetricsAccumulator()
        outcomes: list[ReconOutcome] = []
        batches = 0
        total = len(orders)

        for batch in self._batched(orders, self.config.batch_size):
            processed = self.process_batch(batch, index)
            for outcome in processed:
                metrics.add(outcome)
            if collect_outcomes:
                outcomes.extend(processed)
            if on_batch is not None:
                on_batch(processed)
            batches += 1
            if progress is not None:
                progress(
                    metrics.total_records,
                    total,
                    metrics.matched_records,
                    metrics.exception_records + metrics.unresolved_records,
                )

        # Settlements and bank credits nobody claimed are real findings: money
        # moved without an order behind it. They are appended as UNRESOLVED
        # records rather than dropped.
        orphan_outcomes = self._orphan_outcomes(index)
        for outcome in orphan_outcomes:
            metrics.add(outcome)
        if orphan_outcomes:
            if collect_outcomes:
                outcomes.extend(orphan_outcomes)
            if on_batch is not None:
                on_batch(orphan_outcomes)

        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "reconciled %s records in %sms (%s matched, %s exceptions, %s unresolved)",
            metrics.total_records,
            duration_ms,
            metrics.matched_records,
            metrics.exception_records,
            metrics.unresolved_records,
        )
        return ReconciliationResult(
            metrics=metrics,
            outcomes=outcomes,
            duration_ms=duration_ms,
            batches=batches,
            orphan_settlements=len(orphan_outcomes),
            orphan_bank_rows=len(index.orphan_bank_rows()),
        )

    def process_batch(
        self, orders: Sequence[OrderRecord], index: MatchIndex
    ) -> list[ReconOutcome]:
        """Reconcile one batch of orders against the prebuilt index.

        This is the seam for chunked/parallel processing: it depends only on the
        batch and the (read-mostly) index, never on run-level state.
        """
        return [
            self.reconcile_one(order, match_order(index, order.payment_id, order.order_id))
            for order in orders
        ]

    def reconcile_one(self, order: OrderRecord, match: MatchResult) -> ReconOutcome:
        """The whole business rule for a single order, start to finish."""
        cfg = self.config
        settlement = match.settlement
        currency = order.currency or cfg.currency

        gross = (
            settlement.gross_amount
            if settlement is not None and settlement.gross_amount is not None
            else order.order_amount
        )

        has_bank = bool(match.bank_rows)
        if has_bank:
            settled = match.bank_credit_total
        elif settlement is not None and cfg.allow_settlement_as_actual:
            settled = settlement.settlement_amount
        else:
            settled = 0

        difference = gross - settled
        accounted_for = cfg.accounted_for(settlement)
        unexplained = difference - accounted_for

        facts = Facts(
            expected_amount=gross,
            settled_amount=settled,
            difference=difference,
            fee=settlement.fee if settlement else 0,
            tax=settlement.tax if settlement else 0,
            refund=settlement.refund_amount if settlement else 0,
            adjustment=settlement.adjustment if settlement else 0,
            accounted_for=accounted_for,
            unexplained=unexplained,
            has_settlement=settlement is not None,
            has_bank_credit=has_bank,
            duplicate_settlements=match.duplicate_settlements,
            currency=currency,
        )
        verdict = classify(facts, cfg)

        return ReconOutcome(
            order_id=order.order_id,
            payment_id=order.payment_id,
            settlement_id=settlement.settlement_id if settlement else None,
            bank_reference=match.bank_reference,
            expected_amount=gross,
            settled_amount=settled,
            difference=difference,
            fee=facts.fee,
            tax=facts.tax,
            refund=facts.refund,
            adjustment=facts.adjustment,
            accounted_for=accounted_for,
            unexplained=unexplained,
            status=verdict.status,
            exception_type=verdict.cause.bucket if verdict.cause else None,
            cause=verdict.cause,
            confidence=verdict.confidence,
            reason=verdict.reason,
            currency=currency,
            order_date=order.order_date,
            settlement_date=settlement.settlement_date if settlement else None,
            method=order.method,
            checks=build_checks(facts, match, verdict),
            evidence=self._build_evidence(order, match, facts),
        )

    # -- internals -------------------------------------------------------

    @staticmethod
    def _batched(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
        for start in range(0, len(items), size):
            yield items[start : start + size]

    def _build_evidence(
        self, order: OrderRecord, match: MatchResult, facts: Facts
    ) -> list[ExceptionEvidenceItem]:
        """Cite the source records behind the verdict.

        This payload is the *only* thing the AI layer is given. If a fact is not
        here, the model has no basis to mention it -- which is how we make
        "do not hallucinate" a structural property rather than a prompt request.
        """
        money = lambda v: format_money(v, facts.currency)  # noqa: E731
        settlement = match.settlement
        cap = self.config.max_evidence_fields

        order_fields = [
            ("Order ID", order.order_id),
            ("Payment ID", order.payment_id),
            ("Order amount", money(order.order_amount)),
            ("Order date", order.order_date.isoformat() if order.order_date else "not supplied"),
            ("Status", order.status or "not supplied"),
        ]

        settlement_fields: list[tuple[str, str]] = []
        if settlement is not None:
            settlement_fields = [
                ("Settlement ID", settlement.settlement_id),
                ("Gross", money(settlement.gross_amount) if settlement.gross_amount is not None
                 else "not supplied"),
                ("Net settled", money(settlement.settlement_amount)),
            ]
            for component in self.config.components:
                value = component.value(settlement)
                if value:
                    settlement_fields.append((component.label, money(value)))
            settlement_fields.append(
                ("Settlement date",
                 settlement.settlement_date.isoformat() if settlement.settlement_date
                 else "not supplied")
            )
            if settlement.utr:
                settlement_fields.append(("UTR", settlement.utr))

        bank_fields: list[tuple[str, str]] = []
        if match.bank_rows:
            first = match.bank_rows[0]
            bank_fields = [
                ("Bank transaction ID", first.bank_transaction_id),
                ("Credited", money(match.bank_credit_total)),
                ("UTR", first.utr or "not supplied"),
                ("Value date",
                 first.transaction_date.isoformat() if first.transaction_date else "not supplied"),
            ]
            if first.description:
                bank_fields.append(("Narration", first.description))
            if len(match.bank_rows) > 1:
                bank_fields.append(("Credit lines", str(len(match.bank_rows))))

        return [
            ExceptionEvidenceItem("Orders dataset", order.order_id, True, order_fields[:cap]),
            ExceptionEvidenceItem(
                "Razorpay settlement",
                settlement.settlement_id if settlement else None,
                settlement is not None,
                settlement_fields[:cap],
            ),
            ExceptionEvidenceItem(
                "Bank statement",
                match.bank_reference,
                bool(match.bank_rows),
                bank_fields[:cap],
            ),
        ]

    def _orphan_outcomes(self, index: MatchIndex) -> list[ReconOutcome]:
        """Settlements with no corresponding order, as UNRESOLVED records."""
        outcomes: list[ReconOutcome] = []
        for settlement in index.orphan_settlements():
            bank_rows = index.bank_for(settlement)
            credited = sum(b.credit_amount for b in bank_rows) or settlement.settlement_amount
            # Whichever join key this settlement actually carried -- payment_id
            # when present, else the merchant order reference.
            join_ref = settlement.payment_id or settlement.order_id or settlement.settlement_id
            join_label = "payment ID" if settlement.payment_id else "order reference"
            outcomes.append(
                ReconOutcome(
                    order_id=f"(no order) {join_ref}",
                    payment_id=join_ref,
                    settlement_id=settlement.settlement_id,
                    bank_reference=bank_rows[0].utr if bank_rows else settlement.utr,
                    expected_amount=0,
                    settled_amount=credited,
                    difference=-credited,
                    fee=settlement.fee,
                    tax=settlement.tax,
                    refund=settlement.refund_amount,
                    adjustment=settlement.adjustment,
                    accounted_for=0,
                    unexplained=-credited,
                    status=TxnStatus.UNRESOLVED,
                    exception_type=ExceptionType.UNRESOLVED,
                    cause=ExceptionCause.ORPHAN_SETTLEMENT,
                    confidence=Confidence.HIGH,
                    reason=(
                        f"Settlement {settlement.settlement_id} credits "
                        f"{format_money(credited, settlement.currency)} but no order "
                        f"references its {join_label}."
                    ),
                    currency=settlement.currency,
                    settlement_date=settlement.settlement_date,
                    evidence=[
                        ExceptionEvidenceItem("Orders dataset", None, False, []),
                        ExceptionEvidenceItem(
                            "Razorpay settlement",
                            settlement.settlement_id,
                            True,
                            [
                                ("Settlement ID", settlement.settlement_id),
                                ("Payment ID", settlement.payment_id or settlement.order_id),
                                ("Net settled",
                                 format_money(settlement.settlement_amount, settlement.currency)),
                            ],
                        ),
                    ],
                )
            )
        return outcomes


def reconcile(
    orders: Iterable[OrderRecord],
    settlements: Iterable[SettlementRecord],
    bank_rows: Iterable[BankRecord],
    config: ReconciliationConfig | None = None,
) -> ReconciliationResult:
    """Convenience entry point for tests, notebooks and the benchmark."""
    return ReconciliationEngine(config).run(list(orders), list(settlements), list(bank_rows))
