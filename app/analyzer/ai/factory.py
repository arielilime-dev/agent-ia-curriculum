"""Provider factory: translates settings into a ready-to-use AI provider."""

from __future__ import annotations

import asyncio

import httpx

from app.analyzer.ai.base import AIProvider
from app.analyzer.ai.fallback import FallbackProvider
from app.analyzer.ai.heuristic import HeuristicProvider
from app.analyzer.ai.openai_compatible import OpenAICompatibleProvider
from app.core.config import Settings


class AIConfigurationError(RuntimeError):
    """Raised when the AI configuration is incomplete or inconsistent."""


def build_ai_provider(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> AIProvider:
    """Build the provider described by *settings*.

    ``heuristic`` needs no configuration.  Remote providers require an API key
    (except Ollama) and, for ``openai_compatible``, an explicit base URL.
    """
    if settings.ai_provider == "heuristic":
        return HeuristicProvider()

    base_url = settings.resolved_ai_base_url
    if not base_url:
        raise AIConfigurationError("AI_BASE_URL is required when AI_PROVIDER=openai_compatible")
    if settings.ai_provider != "ollama" and not settings.ai_api_key:
        raise AIConfigurationError(
            f"AI_API_KEY is required when AI_PROVIDER={settings.ai_provider}"
        )

    primary = OpenAICompatibleProvider(
        api_key=settings.ai_api_key or "ollama",
        base_url=base_url,
        model=settings.ai_model,
        name=settings.ai_provider,
        timeout=settings.ai_timeout_seconds,
        max_retries=settings.ai_max_retries,
        temperature=settings.ai_temperature,
        http_client=http_client,
        sleep=asyncio.sleep,
    )
    if settings.ai_fallback_enabled:
        return FallbackProvider(primary, HeuristicProvider())
    return primary
