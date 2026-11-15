"""Fallback chain that keeps the product available when the LLM fails."""

from __future__ import annotations

import logging

from app.analyzer.ai.base import (
    AIInsight,
    AIProvider,
    AIProviderError,
    AnalysisContext,
    mark_degraded,
)

logger = logging.getLogger(__name__)


class FallbackProvider:
    """Try the primary (LLM) provider, then a deterministic fallback."""

    def __init__(self, primary: AIProvider, fallback: AIProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = f"{primary.name}+fallback"
        self.model = fallback.model

    async def analyze(self, context: AnalysisContext) -> AIInsight:
        try:
            insight = await self.primary.analyze(context)
            return insight
        except AIProviderError as exc:
            logger.warning(
                "AI provider '%s' failed (%s); using deterministic fallback",
                self.primary.name,
                exc,
            )
        except Exception:  # noqa: BLE001 - resilience boundary for third-party code
            logger.exception("Unexpected AI provider failure; using deterministic fallback")
        insight = await self.fallback.analyze(context)
        return mark_degraded(insight, provider=f"{self.primary.name}->fallback")
