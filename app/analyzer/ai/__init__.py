"""AI enrichment package."""

from app.analyzer.ai.base import (
    AIInsight,
    AIProvider,
    AIProviderError,
    AnalysisContext,
    mark_degraded,
    parse_insight_payload,
)
from app.analyzer.ai.factory import AIConfigurationError, build_ai_provider
from app.analyzer.ai.fallback import FallbackProvider
from app.analyzer.ai.heuristic import HeuristicProvider
from app.analyzer.ai.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "AIConfigurationError",
    "AIInsight",
    "AIProvider",
    "AIProviderError",
    "AnalysisContext",
    "FallbackProvider",
    "HeuristicProvider",
    "OpenAICompatibleProvider",
    "build_ai_provider",
    "mark_degraded",
    "parse_insight_payload",
]
