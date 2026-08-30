"""Google Gemini provider.

Same contract as the Anthropic/OpenAI providers; different wire format. Talks
to the Generative Language REST API directly over ``httpx`` -- no SDK
dependency, same retry/timeout policy as the others.
"""

from __future__ import annotations

import json
import time
from typing import Any, Sequence

import httpx

from app.ai.base import AIService, AiResult, AiUsage
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.ai.providers.anthropic_provider import _JSON_BLOCK
from app.ai.schemas import AiVerdict, ExceptionFacts
from app.core.errors import ErrorCode, LLMUnavailable
from app.core.logging import get_logger

logger = get_logger(__name__)

_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiAIService(AIService):
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

    def classify_exception(self, facts: ExceptionFacts) -> AiVerdict:
        result = self.explain_exceptions([facts])
        if not result.verdicts:
            raise LLMUnavailable("Model returned no verdict for the exception.")
        return result.verdicts[0]

    def explain_exceptions(self, facts: Sequence[ExceptionFacts]) -> AiResult:
        if not facts:
            return AiResult(verdicts=[], usage=AiUsage(model=self._model))
        payload: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": build_user_prompt(facts)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        body = self._post_with_retry(payload)
        candidates = body.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        text = "".join(p.get("text", "") for p in parts)
        usage = body.get("usageMetadata", {}) or {}
        return AiResult(
            verdicts=self._parse(text, facts),
            usage=AiUsage(model=self._model, tokens=int(usage.get("totalTokenCount", 0))),
        )

    def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = _API_URL.format(model=self._model)
        headers = {"content-type": "application/json"}
        params = {"key": self._api_key}
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
                    continue
                verdict.assert_grounded(source)
            except Exception as exc:
                logger.warning("discarding invalid verdict: %s", exc)
                continue
            verdicts.append(verdict)
        return verdicts
