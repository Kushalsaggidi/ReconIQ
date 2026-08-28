"""The AI layer's guarantees.

Three properties are asserted here, and they are the reason the layer is
separated at all:

1. AI failure never fails a job and never alters a deterministic figure.
2. The model cannot cite a number it was not given.
3. What the engine could not explain stays unexplained and goes to a human.
"""

from __future__ import annotations

from typing import Sequence

import pytest

from app.ai.analyzer import ExceptionAnalyzer, build_facts
from app.ai.base import AIService, AiResult, AiUsage
from app.ai.providers.null_provider import NullAIService
from app.ai.schemas import AiVerdict, ExceptionFacts
from app.core.config import get_settings
from app.core.enums import AiStatus, Confidence, ExceptionType
from app.core.errors import LLMUnavailable
from app.models.entities import ExceptionRecord
from app.storage import repository as repo
from tests.conftest import NET, make_bank, make_order, make_settlement, rupees


# --- fakes ------------------------------------------------------------------

class ExplodingAIService(AIService):
    """Every call fails, the way a rate-limited or unreachable provider does."""

    name = "exploding"

    @property
    def model(self) -> str:
        return "exploding-1"

    def classify_exception(self, facts):
        raise LLMUnavailable("provider is down")

    def explain_exceptions(self, facts):
        raise LLMUnavailable("provider is down")


class SilentAIService(AIService):
    """Returns a well-formed response containing no verdicts."""

    name = "silent"

    @property
    def model(self) -> str:
        return "silent-1"

    def classify_exception(self, facts):
        raise LLMUnavailable("no verdict")

    def explain_exceptions(self, facts: Sequence[ExceptionFacts]) -> AiResult:
        return AiResult(verdicts=[], usage=AiUsage(model=self.model))


# --- helpers ----------------------------------------------------------------

def seed_job(session, job_id: str = "JOB-1"):
    """Reconcile a small set with known exceptions and persist it."""
    from app.reconciliation.engine import reconcile

    orders = [make_order("O-1", "P-1"), make_order("O-2", "P-2"), make_order("O-3", "P-3")]
    settlements = [
        make_settlement("S-1", "P-1", utr="U-1"),
        make_settlement("S-2", "P-2", utr="U-2"),
    ]
    banks = [
        make_bank("B-1", "S-1", credit=NET, utr="U-1"),
        make_bank("B-2", "S-2", credit=NET - rupees(250), utr="U-2"),
    ]
    result = reconcile(orders, settlements, banks)
    repo.create_job(session, job_id, status="running")
    repo.persist_outcomes(session, job_id, result.outcomes)
    session.commit()
    return result


# --- schema validation ------------------------------------------------------

def facts_fixture(**overrides) -> ExceptionFacts:
    base = dict(
        exception_id="exc_1", order_id="O-1", payment_id="P-1", settlement_id="S-1",
        expected_amount=2000.0, actual_amount=1750.0, difference=250.0,
        fee=20.0, tax=3.6, refund=0.0, adjustment=0.0,
        accounted_for=23.6, unexplained=226.4,
        deterministic_type="partial_payment", deterministic_cause="PARTIAL_PAYMENT",
        deterministic_reason="short of expected net settlement",
    )
    base.update(overrides)
    return ExceptionFacts(**base)


def test_unknown_classification_is_rejected():
    with pytest.raises(ValueError, match="not one of"):
        AiVerdict(exception_id="e", classification="chargeback_dispute", explanation="x")


def test_classification_is_normalised():
    verdict = AiVerdict(
        exception_id="e", classification="Partial Payment", explanation="x"
    )
    assert verdict.classification == ExceptionType.PARTIAL_PAYMENT.value


def test_explanation_citing_a_supplied_figure_is_accepted():
    facts = facts_fixture()
    verdict = AiVerdict(
        exception_id="exc_1",
        classification="partial_payment",
        explanation="The bank credited 1750.00 against an expected 2000.00.",
    )
    verdict.assert_grounded(facts)  # must not raise


def test_explanation_citing_an_invented_figure_is_rejected():
    """The structural guard against a hallucinated financial explanation."""
    facts = facts_fixture()
    verdict = AiVerdict(
        exception_id="exc_1",
        classification="partial_payment",
        explanation="A chargeback of 1499.00 explains the shortfall.",
    )
    with pytest.raises(ValueError, match="not among the supplied figures"):
        verdict.assert_grounded(facts)


def test_small_ordinals_are_not_treated_as_monetary_claims():
    facts = facts_fixture()
    verdict = AiVerdict(
        exception_id="exc_1",
        classification="partial_payment",
        explanation="2 of the 4 deterministic checks failed on this record.",
    )
    verdict.assert_grounded(facts)


# --- null provider ----------------------------------------------------------

def test_null_provider_refuses_to_explain_an_unresolved_case():
    verdict = NullAIService().classify_exception(
        facts_fixture(deterministic_type="unresolved", deterministic_cause="UNRESOLVED")
    )

    assert verdict.classification == ExceptionType.UNRESOLVED.value
    assert verdict.requires_human_review is True
    assert verdict.confidence is Confidence.LOW
    assert "no supporting record" in verdict.explanation.lower()


def test_null_provider_explains_a_supported_case_confidently():
    verdict = NullAIService().classify_exception(facts_fixture())

    assert verdict.classification == ExceptionType.PARTIAL_PAYMENT.value
    assert verdict.confidence is Confidence.HIGH
    assert verdict.recommended_action


# --- analyzer resilience ----------------------------------------------------

def test_ai_failure_does_not_lose_deterministic_results(session):
    result = seed_job(session)
    before = {
        (r.order_id, r.unexplained, r.exception_type)
        for r in session.query(ExceptionRecord).all()
    }

    summary = ExceptionAnalyzer(ExplodingAIService(), get_settings()).analyse_job(
        session, "JOB-1"
    )
    session.commit()

    after = {
        (r.order_id, r.unexplained, r.exception_type)
        for r in session.query(ExceptionRecord).all()
    }
    assert after == before                      # not one figure moved
    assert summary["analysed"] == 0
    assert summary["failed"] == len(before)
    assert result.metrics.total_records == 3

    for record in session.query(ExceptionRecord).all():
        assert record.ai_status == AiStatus.FAILED.value
        assert record.ai_error
        assert record.requires_human_review is True


def test_a_response_with_no_verdicts_marks_the_batch_failed(session):
    seed_job(session)
    summary = ExceptionAnalyzer(SilentAIService(), get_settings()).analyse_job(
        session, "JOB-1"
    )
    session.commit()

    assert summary["analysed"] == 0
    assert all(
        r.ai_status == AiStatus.FAILED.value for r in session.query(ExceptionRecord).all()
    )


def test_successful_analysis_populates_advisory_fields_only(session):
    seed_job(session)
    before = {r.id: (r.expected_amount, r.actual_amount, r.unexplained)
              for r in session.query(ExceptionRecord).all()}

    summary = ExceptionAnalyzer(NullAIService(), get_settings()).analyse_job(
        session, "JOB-1"
    )
    session.commit()

    assert summary["analysed"] == len(before)
    for record in session.query(ExceptionRecord).all():
        assert record.ai_status == AiStatus.COMPLETED.value
        assert record.ai_explanation and record.ai_classification
        assert record.ai_model == "deterministic-explainer-v1"
        # The money columns are byte-identical to before the AI ran.
        assert (record.expected_amount, record.actual_amount, record.unexplained) == before[record.id]


def test_unresolved_records_stay_flagged_for_humans_even_when_ai_succeeds(session):
    seed_job(session)
    ExceptionAnalyzer(NullAIService(), get_settings()).analyse_job(session, "JOB-1")
    session.commit()

    unresolved = session.query(ExceptionRecord).filter_by(order_id="O-3").one()
    assert unresolved.exception_type == ExceptionType.UNRESOLVED.value
    assert unresolved.requires_human_review is True


def test_only_exceptions_are_ever_sent_to_the_model(session):
    """The volume guarantee: matched records never reach the AI layer."""
    seed_job(session)
    pending = repo.iter_exceptions_for_ai(session, "JOB-1", limit=100)

    assert len(pending) == 2                      # O-2 and O-3, never O-1
    assert {r.order_id for r in pending} == {"O-2", "O-3"}


def test_the_per_job_cap_is_enforced(session):
    seed_job(session)
    assert len(repo.iter_exceptions_for_ai(session, "JOB-1", limit=1)) == 1


def test_facts_payload_carries_no_raw_source_rows(session):
    seed_job(session)
    record = session.query(ExceptionRecord).filter_by(order_id="O-2").one()
    facts = build_facts(record)

    assert facts.expected_amount == 2000.0
    assert facts.unexplained == 250.0
    # Only computed figures, checks and presence flags -- no source row escapes.
    assert set(facts.model_dump()) == {
        "exception_id", "order_id", "payment_id", "settlement_id", "currency",
        "expected_amount", "actual_amount", "difference", "fee", "tax", "refund",
        "adjustment", "accounted_for", "unexplained", "deterministic_type",
        "deterministic_cause", "deterministic_reason", "checks", "evidence_present",
    }
