"""Google Gemini tool-calling Copilot provider.

Talks to the same Generative Language REST API as
:class:`app.ai.providers.gemini_provider.GeminiAIService`, over ``httpx``, with
the same retry/timeout policy -- but drives an agentic tool-calling loop
instead of a single classify-and-explain call. The model decides which
read-only tool it needs; this file only ever executes the tool the caller gave
it (see ``tool_runner``) and never gives the model raw SQL or database access.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.copilot.provider_base import ChatMessage, CopilotProvider, ProviderTurn, ToolRunner
from app.copilot.tools import ToolCallResult, ToolSpec
from app.core.errors import ErrorCode, LLMUnavailable
from app.core.logging import get_logger

logger = get_logger(__name__)

_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
#: Hard ceiling on tool-calling round-trips per question. Bounds latency and
#: cost, and guarantees the loop terminates even if the model keeps calling
#: tools instead of answering.
MAX_TOOL_HOPS = 4


class GeminiCopilotProvider(CopilotProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise LLMUnavailable(
                "LLM_PROVIDER=gemini but LLM_API_KEY is empty.",
                code=ErrorCode.LLM_UNAVAILABLE,
            )
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries

    @property
    def model(self) -> str:
        return self._model

    def converse(
        self,
        *,
        system_prompt: str,
        history: list[ChatMessage],
        message: str,
        tools: list[ToolSpec],
        tool_runner: ToolRunner,
    ) -> ProviderTurn:
        contents: list[dict[str, Any]] = [
            {"role": "user" if m.role == "user" else "model", "parts": [{"text": m.content}]}
            for m in history
        ]
        contents.append({"role": "user", "parts": [{"text": message}]})

        tool_declarations = [{"functionDeclarations": [t.declaration() for t in tools]}]
        tool_calls: list[ToolCallResult] = []
        total_tokens = 0

        for _hop in range(MAX_TOOL_HOPS):
            body = self._post_with_retry(system_prompt, contents, tool_declarations)
            total_tokens += _usage_tokens(body)

            parts = _first_candidate_parts(body)
            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            text = "".join(p.get("text", "") for p in parts if "text" in p)

            if not calls:
                if not text.strip():
                    raise LLMUnavailable("Model returned neither a tool call nor an answer.")
                return ProviderTurn(answer=text.strip(), tool_calls=tool_calls, tokens=total_tokens)

            # Record the model's own tool-call turn verbatim -- including any
            # sibling fields (e.g. `thoughtSignature`) this model attaches
            # next to a functionCall part, which it requires echoed back
            # unmodified on the next turn. Stripping to just {"functionCall"}
            # is rejected outright by newer ("thinking") Gemini models.
            contents.append({"role": "model", "parts": parts})
            response_parts = []
            for call in calls:
                name = call.get("name", "")
                args = call.get("args") or {}
                result = tool_runner(name, args)
                tool_calls.append(result)
                response_parts.append({"functionResponse": {"name": name, "response": result.data}})
            # This API rejects a dedicated "function" role outright ("Role
            # 'function' is not supported") -- a tool result is sent back as
            # a "user" turn instead, distinguished from real user text only
            # by containing functionResponse parts.
            contents.append({"role": "user", "parts": response_parts})

        # Hit the hop cap without a final answer: ask once more with tools
        # withheld, forcing the model to summarise what it already has rather
        # than loop forever.
        body = self._post_with_retry(system_prompt, contents, tools=None)
        text = "".join(p.get("text", "") for p in _first_candidate_parts(body) if "text" in p).strip()
        if not text:
            raise LLMUnavailable("Model did not produce a final answer within the tool-call limit.")
        return ProviderTurn(answer=text, tool_calls=tool_calls, tokens=total_tokens)

    # -- internals ---------------------------------------------------------

    def _post_with_retry(
        self,
        system_prompt: str,
        contents: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        url = _API_URL.format(model=self._model)
        headers = {"content-type": "application/json"}
        params = {"key": self._api_key}
        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0},
        }
        if tools:
            payload["tools"] = tools

        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = httpx.post(
                    url, json=payload, headers=headers, params=params, timeout=self._timeout
                )
                if response.status_code in (429, 500, 502, 503):
                    raise httpx.HTTPStatusError(
                        f"retryable status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                if attempt < self._max_retries:
                    time.sleep(0.75 * (attempt + 1))
        raise LLMUnavailable(
            f"Gemini request failed after {self._max_retries + 1} attempt(s): {last}",
            code=ErrorCode.LLM_UNAVAILABLE,
        )


def _first_candidate_parts(body: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = body.get("candidates") or []
    if not candidates:
        return []
    return candidates[0].get("content", {}).get("parts", []) or []


def _usage_tokens(body: dict[str, Any]) -> int:
    usage = body.get("usageMetadata", {}) or {}
    return int(usage.get("totalTokenCount", 0))


__all__ = ["GeminiCopilotProvider", "MAX_TOOL_HOPS"]
