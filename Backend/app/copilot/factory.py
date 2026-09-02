"""Copilot provider selection.

Mirrors :mod:`app.ai.factory` exactly: reads the same ``LLM_PROVIDER`` /
``LLM_API_KEY`` / ``MODEL_NAME`` settings the exception analyser uses -- no
duplicated configuration -- and falls back to the deterministic Copilot rather
than leaving the feature unavailable if the configured provider cannot be
constructed. A degraded, keyword-routed answer is more useful than a 500, and
it is what keeps this endpoint safe to call even with no API key configured.

Only Gemini has an agentic tool-calling implementation today (it is the
provider named throughout the Copilot's design). Anthropic/OpenAI are valid
choices for the exception analyser but fall back to the deterministic Copilot
here until a tool-calling implementation is added for them.
"""

from __future__ import annotations

from app.copilot.provider_base import CopilotProvider
from app.copilot.providers.null_provider import NullCopilotProvider
from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_cached: CopilotProvider | None = None


def build_copilot_provider(settings: Settings | None = None) -> CopilotProvider:
    settings = settings or get_settings()
    provider = settings.llm_provider

    try:
        if provider == "gemini":
            from app.copilot.providers.gemini_provider import GeminiCopilotProvider

            return GeminiCopilotProvider(
                settings.llm_api_key,
                settings.model_name,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
        if provider in ("anthropic", "openai"):
            logger.info(
                "Copilot has no tool-calling implementation for provider '%s' yet; "
                "using the deterministic Copilot.", provider,
            )
            return NullCopilotProvider()
    except Exception as exc:
        logger.warning(
            "Copilot provider '%s' unavailable (%s); using the deterministic Copilot.",
            provider, exc,
        )
        return NullCopilotProvider()

    return NullCopilotProvider()


def get_copilot_provider() -> CopilotProvider:
    global _cached
    if _cached is None:
        _cached = build_copilot_provider()
    return _cached


def set_copilot_provider(provider: CopilotProvider | None) -> None:
    """Test hook -- inject a failing or stub provider."""
    global _cached
    _cached = provider


__all__ = ["build_copilot_provider", "get_copilot_provider", "set_copilot_provider"]
