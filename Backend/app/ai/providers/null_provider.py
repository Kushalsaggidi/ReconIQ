"""Deterministic, offline explainer.

Not a mock: it is the default provider, and it is what makes the system
demonstrable with no API key, no network and no cost.  It writes the same
sentence a careful analyst would write from the deterministic verdict -- and,
crucially, it refuses to explain anything the engine classified as unresolved.

That refusal is the behaviour the whole AI layer is designed around, so it is
worth having it available without a model in the loop.
"""

from __future__ import annotations

from typing import Sequence

from app.ai.base import AIService, AiResult, AiUsage
from app.ai.schemas import AiVerdict, ExceptionFacts
from app.core.enums import Confidence, ExceptionType

_TEMPLATES: dict[str, str] = {
    ExceptionType.FEE_TAX.value: (
        "The shortfall corresponds to the platform fee and tax declared on the "
        "settlement record. The deduction is legitimate but was not reflected "
        "in the expected net, so the two sides disagree by exactly that amount."
    ),
    ExceptionType.REFUND.value: (
        "A refund declared on the settlement record accounts for the variance. "
        "The refund appears to have been applied on one side of the "
        "reconciliation only."
    ),
    ExceptionType.ROUNDING.value: (
        "The residual is within the configured rounding tolerance and is "
        "consistent with per-transaction rounding on the settlement side. No "
        "action is normally required."
    ),
    ExceptionType.PARTIAL_PAYMENT.value: (
        "Less was credited than the order and its declared deductions justify, "
        "and no fee, tax or refund on the settlement record accounts for the "
        "gap. This is consistent with a partial or split settlement."
    ),
    ExceptionType.UNRESOLVED.value: (
        "No supporting record explains this variance. The engine did not infer "
        "a cause and no value has been assumed. This requires human review."
    ),
}

_ACTIONS: dict[str, str] = {
    ExceptionType.FEE_TAX.value: "Confirm the fee schedule applied and adjust the expected net.",
    ExceptionType.REFUND.value: "Verify the refund in the refund ledger and reconcile the double entry.",
    ExceptionType.ROUNDING.value: "No action required; monitor if the pattern recurs at scale.",
    ExceptionType.PARTIAL_PAYMENT.value: "Check for a later settlement covering the balance before escalating.",
    ExceptionType.UNRESOLVED.value: "Assign to a treasury analyst; request the missing source record.",
}


class NullAIService(AIService):
    name = "null"

    @property
    def model(self) -> str:
        return "deterministic-explainer-v1"

    def classify_exception(self, facts: ExceptionFacts) -> AiVerdict:
        kind = facts.deterministic_type
        unresolved = kind == ExceptionType.UNRESOLVED.value
        signals = [
            c.get("label", "")
            for c in facts.checks
            if isinstance(c, dict) and not c.get("passed", True)
        ][:4]
        if not signals:
            signals = [
                f"{source} record present"
                for source, present in facts.evidence_present.items()
                if present
            ][:4]

        return AiVerdict(
            exception_id=facts.exception_id,
            classification=kind,
            explanation=_TEMPLATES.get(kind, _TEMPLATES[ExceptionType.UNRESOLVED.value]),
            # Mirror the engine's own confidence rather than asserting more
            # than the deterministic layer did.
            confidence=Confidence.LOW if unresolved else Confidence.HIGH,
            signals=signals,
            recommended_action=_ACTIONS.get(kind, _ACTIONS[ExceptionType.UNRESOLVED.value]),
            requires_human_review=unresolved,
        )

    def explain_exceptions(self, facts: Sequence[ExceptionFacts]) -> AiResult:
        return AiResult(
            verdicts=[self.classify_exception(f) for f in facts],
            usage=AiUsage(model=self.model, tokens=0),
        )
