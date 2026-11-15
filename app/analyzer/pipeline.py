"""End-to-end analysis pipeline: parse -> score -> AI enrich -> merge."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.analyzer.ai.base import (
    AIInsight,
    AIProvider,
    AIProviderError,
    AnalysisContext,
    mark_degraded,
)
from app.analyzer.ai.heuristic import HeuristicProvider
from app.analyzer.parser import ParsedResume, ResumeParser
from app.analyzer.scoring import score_resume
from app.analyzer.text import normalize

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisOutcome:
    """Everything the service layer persists after an analysis run."""

    parsed: ParsedResume
    result: dict[str, Any]
    ai_provider: str
    ai_model: str
    ai_degraded: bool
    ai_confidence: float


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = normalize(value)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


class ResumeAnalysisPipeline:
    """Coordinates parsing, deterministic scoring and AI enrichment."""

    def __init__(self, provider: AIProvider, *, parser: ResumeParser | None = None) -> None:
        self.provider = provider
        self.parser = parser or ResumeParser()
        self._fallback_provider = HeuristicProvider()

    async def analyze(
        self,
        text: str,
        *,
        job_description: str | None = None,
        job_title: str | None = None,
        now: datetime | None = None,
    ) -> AnalysisOutcome:
        cleaned = (text or "").strip()
        parsed = self.parser.parse(cleaned, now=now)
        result = score_resume(
            parsed,
            job_description=job_description,
            job_title=job_title,
            resume_text=cleaned,
            now=now,
        )
        context = AnalysisContext(
            resume_text=cleaned,
            parsed=parsed,
            result=result,
            job_description=job_description,
            job_title=job_title,
        )

        insight = await self._get_insight(context)
        if insight.summary:
            result["summary"] = insight.summary[:1200]
        result["strengths"] = _dedupe([*result.get("strengths", []), *insight.strengths])[:8]
        result["suggestions"] = _dedupe([*result.get("suggestions", []), *insight.improvements])[
            :10
        ]
        result["ai"] = {
            "provider": insight.provider,
            "model": insight.model,
            "degraded": insight.degraded,
            "confidence": insight.confidence,
        }

        return AnalysisOutcome(
            parsed=parsed,
            result=result,
            ai_provider=insight.provider,
            ai_model=insight.model,
            ai_degraded=insight.degraded,
            ai_confidence=insight.confidence,
        )

    async def _get_insight(self, context: AnalysisContext) -> AIInsight:
        try:
            return await self.provider.analyze(context)
        except AIProviderError as exc:
            logger.warning("AI provider failed (%s); falling back to rules", exc)
        except Exception:  # noqa: BLE001 - keep analyses available even if a provider breaks
            logger.exception("Unexpected AI provider error; falling back to rules")
        insight = await self._fallback_provider.analyze(context)
        return mark_degraded(insight, provider=f"{self.provider.name}->fallback")
