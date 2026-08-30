"""Provider selection.

The single place that reads ``LLM_PROVIDER``.  If a configured provider cannot
be constructed -- missing key, unknown name -- we log it and fall back to the
deterministic explainer rather than leaving the system with no AI layer at all.
A degraded explanation is more useful than a 500.
"""

from __future__ import annotations

from app.ai.base import AIService
from app.ai.providers.null_provider import NullAIService
from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_cached: AIService | None = None


def build_ai_service(settings: Settings | None = None) -> AIService:
    settings = settings or get_settings()
    provider = settings.llm_provider

    try:
        if provider == "anthropic":
            from app.ai.providers.anthropic_provider import AnthropicAIService

            return AnthropicAIService(
                settings.llm_api_key,
                settings.model_name,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
        if provider == "openai":
            from app.ai.providers.openai_provider import OpenAIAIService

            return OpenAIAIService(
                settings.llm_api_key,
                settings.model_name,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
        if provider == "gemini":
            from app.ai.providers.gemini_provider import GeminiAIService

            return GeminiAIService(
                settings.llm_api_key,
                settings.model_name,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
    except Exception as exc:
        logger.warning(
            "LLM provider '%s' unavailable (%s); using the deterministic explainer.",
            provider, exc,
        )
        return NullAIService()

    return NullAIService()


def get_ai_service() -> AIService:
    global _cached
    if _cached is None:
        _cached = build_ai_service()
    return _cached


def set_ai_service(service: AIService | None) -> None:
    """Test hook -- inject a failing or stub provider."""
    global _cached
    _cached = service
