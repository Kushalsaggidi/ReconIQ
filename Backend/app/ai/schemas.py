"""Structured facts in, validated JSON out.

Two contracts:

``ExceptionFacts``   what the model is given -- already-computed figures only.
``AiVerdict``        what the model must return -- validated before it is stored.

The model is never asked to produce a monetary value.  Every number it might
mention already exists in the facts payload, so an "explanation" containing a
figure we did not supply is, by construction, a hallucination.  Validation
rejects those.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.enums import Confidence, ExceptionType

#: The only classifications the model may return.
ALLOWED_CLASSIFICATIONS: tuple[str, ...] = tuple(e.value for e in ExceptionType)


class ExceptionFacts(BaseModel):
    """The payload sent to the LLM.  Nothing here is model-generated."""

    exception_id: str
    order_id: str
    payment_id: str
    settlement_id: str | None = None

    currency: str = "INR"
    expected_amount: float
    actual_amount: float
    difference: float
    fee: float
    tax: float
    refund: float
    adjustment: float
    accounted_for: float
    unexplained: float

    deterministic_type: str
    deterministic_cause: str | None = None
    deterministic_reason: str
    checks: list[dict[str, Any]] = Field(default_factory=list)
    evidence_present: dict[str, bool] = Field(default_factory=dict)

    def numeric_vocabulary(self) -> set[str]:
        """Every figure the model is permitted to cite, as formatted strings.

        Used by :meth:`AiVerdict.assert_grounded` to catch invented amounts.
        """
        values = {
            self.expected_amount,
            self.actual_amount,
            self.difference,
            self.fee,
            self.tax,
            self.refund,
            self.adjustment,
            self.accounted_for,
            self.unexplained,
        }
        vocab: set[str] = set()
        for v in values:
            vocab.add(f"{abs(v):.2f}")
            vocab.add(f"{abs(v):.0f}")
            vocab.add(f"{abs(v):,.2f}")
            vocab.add(f"{abs(v):,.0f}")
        return vocab


class AiVerdict(BaseModel):
    """Validated LLM output.  Advisory only -- never written to a money column."""

    exception_id: str
    classification: str
    explanation: str = Field(min_length=1, max_length=1200)
    confidence: Confidence = Confidence.LOW
    #: Which supplied evidence supports the explanation.
    signals: list[str] = Field(default_factory=list, max_length=8)
    recommended_action: str = Field(default="", max_length=400)
    #: Set when the model declines to explain -- a legitimate, expected answer.
    requires_human_review: bool = False

    @field_validator("classification")
    @classmethod
    def _known_classification(cls, v: str) -> str:
        slug = str(v).strip().lower().replace(" ", "_").replace("-", "_")
        if slug not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(
                f"classification '{v}' is not one of {ALLOWED_CLASSIFICATIONS}"
            )
        return slug

    @field_validator("signals")
    @classmethod
    def _trim_signals(cls, v: list[str]) -> list[str]:
        return [str(s).strip()[:160] for s in v if str(s).strip()][:8]

    def assert_grounded(self, facts: ExceptionFacts) -> None:
        """Reject an explanation that cites a figure we never supplied.

        This is the structural guard behind "never hallucinate a financial
        explanation": we cannot police prose, but we can police arithmetic.
        """
        vocab = facts.numeric_vocabulary()
        cited = re.findall(r"\d[\d,]*(?:\.\d+)?", self.explanation)
        for token in cited:
            bare = token.strip(",")
            if bare in vocab or bare.replace(",", "") in {v.replace(",", "") for v in vocab}:
                continue
            # Percentages and small ordinals ("2 records", "100%") are not
            # monetary claims; only reject figures that look like amounts.
            if len(bare.replace(",", "").split(".")[0]) <= 2:
                continue
            raise ValueError(
                f"explanation cites '{token}', which is not among the supplied figures"
            )


class AiBatchResponse(BaseModel):
    verdicts: list[AiVerdict] = Field(default_factory=list)
