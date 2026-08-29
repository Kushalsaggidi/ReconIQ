"""LLM provider abstraction.

Every provider implements two methods and nothing else.  Swapping Anthropic for
OpenAI (or for the deterministic ``NullAIService``) is a config change:

    LLM_PROVIDER=anthropic

Providers may raise; they may time out; they may return nonsense.  All three are
handled by the caller (:mod:`app.ai.analyzer`) and none of them can fail a
reconciliation job.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from app.ai.schemas import AiVerdict, ExceptionFacts


@dataclass(slots=True)
class AiUsage:
    model: str
    tokens: int = 0


@dataclass(slots=True)
class AiResult:
    verdicts: list[AiVerdict]
    usage: AiUsage


class AIService(ABC):
    """Contract for anything that classifies and explains exceptions."""

    name: str = "base"

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    def classify_exception(self, facts: ExceptionFacts) -> AiVerdict:
        """Classify and explain a single exception."""

    @abstractmethod
    def explain_exceptions(self, facts: Sequence[ExceptionFacts]) -> AiResult:
        """Classify and explain a batch.  Batching is what keeps cost sane."""

    def health(self) -> dict[str, object]:
        return {"provider": self.name, "model": self.model, "available": True}
