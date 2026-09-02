"""Response validation -- the structural guard against a hallucinated answer.

Mirrors the guarantee ``app/ai/schemas.py::AiVerdict.assert_grounded`` gives the
exception analyser: the model is never trusted to only cite real figures on
its own, so its final answer is checked against the numbers the tools it
called in *this* conversation actually returned. A citation to a figure
nobody supplied is rejected outright -- the caller falls back to a safe
message rather than showing an unverified answer (see ``app/copilot/service.py``).

A second, independent guard rejects any claim that the Copilot performed a
write action. The Copilot has no write tools, so such a claim is unsafe
regardless of how it was produced -- a confused model, a stale response, or a
prompt-injection attempt from data inside a tool result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

#: Adjacent characters that mean "this digit run is part of an identifier,
#: date or timestamp, not a monetary figure" -- e.g. the "1042" in "ORD-1042",
#: the "09" in "2026-09-02", or the "15" in "10:15:00".
_ID_LIKE_BOUNDARY = re.compile(r"[A-Za-z0-9\-_/:]")

#: Phrases that claim a write action. If the Copilot's text ever contains one
#: of these, the response is unsafe -- it has no tool capable of doing this.
_BANNED_WRITE_PHRASES: tuple[str, ...] = (
    "i have marked", "i've marked", "i have resolved", "i've resolved",
    "marked as resolved", "i have updated", "i've updated", "i have changed",
    "i've changed", "i have deleted", "i've deleted", "status has been updated",
    "i will resolve", "resolving this now", "i have reversed", "i've reversed",
    "payment has been reversed", "has been marked resolved", "i've closed",
    "i have closed this", "i've fixed", "i have fixed",
)


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    reason: str | None = None


def _walk_numbers(value: Any, out: set[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.add(f"{abs(value):.2f}")
        out.add(f"{abs(value):.0f}")
        out.add(f"{abs(value):,.2f}")
        out.add(f"{abs(value):,.0f}")
        out.add(f"{abs(value)}")
    elif isinstance(value, dict):
        for v in value.values():
            _walk_numbers(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk_numbers(v, out)


def numeric_vocabulary(tool_results: Iterable[dict[str, Any]]) -> set[str]:
    """Every figure the model is permitted to cite, as formatted strings."""
    vocab: set[str] = set()
    for result in tool_results:
        _walk_numbers(result, vocab)
    return vocab


def _cited_amounts(text: str) -> list[str]:
    """Numeric tokens in ``text`` that *look like* monetary claims.

    Skips digit runs glued to a letter, hyphen, underscore, slash or colon on
    either side -- those are identifiers ("ORD-1042"), dates
    ("2026-09-02") or timestamps ("10:15:00"), not amounts.
    """
    tokens: list[str] = []
    for match in _NUMBER_RE.finditer(text):
        start, end = match.span()
        before = text[start - 1] if start > 0 else ""
        after = text[end] if end < len(text) else ""
        if _ID_LIKE_BOUNDARY.match(before) or _ID_LIKE_BOUNDARY.match(after):
            continue
        tokens.append(match.group(0))
    return tokens


def validate_answer(
    answer: str,
    *,
    tool_results: list[dict[str, Any]],
    user_message: str,
) -> ValidationResult:
    """Reject an answer that claims a write action or cites an invented figure."""
    lowered = answer.lower()
    for phrase in _BANNED_WRITE_PHRASES:
        if phrase in lowered:
            return ValidationResult(
                ok=False,
                reason=f"answer contains a write-action claim ('{phrase}'), but the Copilot is read-only",
            )

    if not tool_results:
        # No tool was called: typically a scoped refusal, a clarifying
        # question, or "I need a reconciliation to answer that". There is
        # nothing supplied to check numbers against, so we don't number-police
        # a response that made no factual claim about this job's data.
        return ValidationResult(ok=True)

    vocab = numeric_vocabulary(tool_results)
    allowed_from_user = set(_NUMBER_RE.findall(user_message))
    for token in _cited_amounts(answer):
        bare = token.strip(",")
        normalised = bare.replace(",", "")
        if bare in vocab or normalised in {v.replace(",", "") for v in vocab}:
            continue
        if token in allowed_from_user:
            continue
        # Small integers (record counts, rounded percentages, ordinals) are
        # not monetary claims -- same heuristic as the exception analyser.
        if len(normalised.split(".")[0]) <= 2:
            continue
        return ValidationResult(
            ok=False,
            reason=f"answer cites '{token}', which was not returned by any tool call in this conversation",
        )
    return ValidationResult(ok=True)


__all__ = ["ValidationResult", "validate_answer", "numeric_vocabulary"]
