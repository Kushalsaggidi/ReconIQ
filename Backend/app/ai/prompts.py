"""Prompt construction.

Kept in one file so the prompt is reviewable as a policy document rather than
buried in a provider.  The system prompt states the rules the schema layer then
*enforces* -- we ask nicely and verify afterwards.
"""

from __future__ import annotations

import json
from typing import Sequence

from app.ai.schemas import ALLOWED_CLASSIFICATIONS, ExceptionFacts

SYSTEM_PROMPT = """You are a settlement reconciliation analyst.

A deterministic engine has already matched the records and computed every
figure. Your job is ONLY to classify and explain. Specifically:

1. You must NOT perform arithmetic. Every number you need is supplied.
2. You must NOT introduce any figure that is not in the supplied facts.
3. You must NOT claim a record is reconciled, settled, or resolved.
4. If the supplied evidence does not support a specific explanation, classify
   it as "unresolved", set requires_human_review to true, and say plainly that
   no supporting record explains the variance. This is a correct answer, not a
   failure. Never invent a plausible-sounding cause.
5. "signals" must quote only check labels or evidence sources that appear in
   the supplied facts.

Valid classifications: {classifications}

Return ONLY a JSON object of this exact shape, with no prose around it:

{{"verdicts": [
  {{"exception_id": "...",
    "classification": "one of the valid classifications",
    "explanation": "two or three plain sentences for a finance operator",
    "confidence": "high" | "medium" | "low",
    "signals": ["evidence that supports this"],
    "recommended_action": "what a human should do next",
    "requires_human_review": true | false}}
]}}""".format(classifications=", ".join(ALLOWED_CLASSIFICATIONS))


def build_user_prompt(facts: Sequence[ExceptionFacts]) -> str:
    """Serialise a batch of facts.  Only exceptions are ever sent -- never a
    whole dataset, and never a raw source row."""
    payload = [f.model_dump(mode="json") for f in facts]
    return (
        f"Classify and explain the following {len(payload)} reconciliation "
        "exception(s). All amounts are in the record's own currency and are "
        "final: do not recompute them.\n\n"
        f"{json.dumps(payload, indent=2, default=str)}"
    )
