"""Anthropic (Claude) provider.

Talks to the Messages API over ``httpx`` rather than pulling in the SDK, so the
dependency surface stays small and the retry/timeout policy is ours.

Every failure mode here raises :class:`LLMUnavailable`; nothing in this file can
fail a reconciliation job.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Sequence

import httpx

from app.ai.base import AIService, AiResult, AiUsage
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.ai.schemas import AiVerdict, ExceptionFacts
from app.core.errors import ErrorCode, LLMUnavailable
from app.core.logging import get_logger

logger = get_logger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
#: Models sometimes wrap JSON in prose or a fence despite instructions.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class AnthropicAIService(AIService):
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-5",
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
        max_tokens: int = 4096,
    ) -> None:
        if not api_key:
            raise LLMUnavailable(
                "LLM_PROVIDER=anthropic but LLM_API_KEY is empty.",
                code=ErrorCode.LLM_UNAVAILABLE,
            )
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    def classify_exception(self, facts: ExceptionFacts) -> AiVerdict:
        result = self.explain_exceptions([facts])
        if not result.verdicts:
            raise LLMUnavailable("Model returned no verdict for the exception.")
        return result.verdicts[0]

    def explain_exceptions(self, facts: Sequence[ExceptionFacts]) -> AiResult:
        if not facts:
            return AiResult(verdicts=[], usage=AiUsage(model=self._model))
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": SYSTEM_PROMPT,
            "temperature": 0,
            "messages": [{"role": "user", "content": build_user_prompt(facts)}],
        }
        body = self._post_with_retry(payload)
        text = "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        )
        usage = body.get("usage", {}) or {}
        return AiResult(
            verdicts=self._parse(text, facts),
            usage=AiUsage(
                model=self._model,
                tokens=int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)),
            ),
        )

    # -- internals -------------------------------------------------------

    def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = httpx.post(
                    _API_URL, json=payload, headers=headers, timeout=self._timeout
                )
                if response.status_code in (429, 500, 502, 503, 529):
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
                    # Linear backoff is enough here: the batch is small and the
                    # caller already treats total failure as non-fatal.
                    time.sleep(0.75 * (attempt + 1))
        raise LLMUnavailable(
            f"Anthropic request failed after {self._max_retries + 1} attempt(s): {last}",
            code=ErrorCode.LLM_UNAVAILABLE,
        )

    @staticmethod
    def _parse(text: str, facts: Sequence[ExceptionFacts]) -> list[AiVerdict]:
        match = _JSON_BLOCK.search(text or "")
        if not match:
            raise LLMUnavailable("Model response contained no JSON object.")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMUnavailable(f"Model returned invalid JSON: {exc}") from exc

        raw = data.get("verdicts", data if isinstance(data, list) else [])
        by_id = {f.exception_id: f for f in facts}
        verdicts: list[AiVerdict] = []
        for item in raw:
            try:
                verdict = AiVerdict.model_validate(item)
                source = by_id.get(verdict.exception_id)
                if source is None:
                    # A verdict for an exception we never sent is discarded
                    # rather than trusted.
                    logger.warning("discarding verdict for unknown exception %s",
                                   verdict.exception_id)
                    continue
                verdict.assert_grounded(source)
            except Exception as exc:  # per-item: one bad verdict is not fatal
                logger.warning("discarding invalid verdict: %s", exc)
                continue
            verdicts.append(verdict)
        return verdicts
