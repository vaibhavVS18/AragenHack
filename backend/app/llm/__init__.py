"""LLM provider implementations for the Explain step.

``get_provider`` is the only thing the agent imports: it resolves the
configured provider so no other module needs to know which one is active.
"""

from __future__ import annotations

from ..config import Settings
from .base import Explanation, LLMProvider, LLMUnavailableError
from .mock import MockProvider

__all__ = [
    "Explanation",
    "LLMProvider",
    "LLMUnavailableError",
    "MockProvider",
    "get_provider",
]


def get_provider(settings: Settings) -> LLMProvider:
    """Return the provider selected by ``LLM_PROVIDER``.

    Falls back to the offline mock when Gemini is selected without an API key,
    so a missing key degrades the demo instead of breaking startup. The
    substitution is visible in the API response metadata.
    """
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key.strip():
            return MockProvider()

        # Imported lazily so the Gemini SDK is only loaded when actually used.
        from .gemini import GeminiProvider

        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    return MockProvider()
