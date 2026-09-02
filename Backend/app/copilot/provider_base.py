"""Copilot provider abstraction.

Same spirit as :mod:`app.ai.base`: one contract, swappable providers, and a
caller (:mod:`app.copilot.service`) that handles every failure mode so a
broken or unavailable model can never break the base application.

Unlike :class:`app.ai.base.AIService` (single-shot classify/explain), a
Copilot provider runs an agentic tool-calling loop: it is handed the
conversation so far and a set of read-only tools, and must return a final
natural-language answer plus a log of which tools it called -- never a
financial figure it invented itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Literal

from app.copilot.tools import ToolCallResult, ToolSpec

Role = Literal["user", "assistant"]


@dataclass(slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(slots=True)
class ProviderTurn:
    """One finished Copilot turn."""

    answer: str
    tool_calls: list[ToolCallResult] = field(default_factory=list)
    tokens: int = 0


#: Executes one tool call by name; already bound to a session and job id by
#: the caller, so a provider can never pass its own job id.
ToolRunner = Callable[[str, dict], ToolCallResult]


class CopilotProvider(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    def converse(
        self,
        *,
        system_prompt: str,
        history: list[ChatMessage],
        message: str,
        tools: list[ToolSpec],
        tool_runner: ToolRunner,
    ) -> ProviderTurn:
        """Answer ``message`` given the conversation ``history``.

        May call ``tool_runner`` any number of times before returning. Should
        raise :class:`app.core.errors.LLMUnavailable` only for a genuine
        transport/provider failure (timeout, bad key, malformed response) --
        never for "the model said something we don't like", which is the
        grounding layer's job, not the provider's.
        """

    def health(self) -> dict[str, object]:
        return {"provider": self.name, "model": self.model, "available": True}


__all__ = ["ChatMessage", "ProviderTurn", "ToolRunner", "CopilotProvider"]
