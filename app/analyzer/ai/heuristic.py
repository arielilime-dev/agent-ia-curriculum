"""Deterministic, offline "AI" provider.

It reuses the rule-based analyzer output to produce an insight with the same
shape as an LLM response.  This guarantees the product works without any API
key, provides a safe fallback when the remote provider fails, and gives tests a
stable oracle.
"""

from __future__ import annotations

from app.analyzer.ai.base import AIInsight, AnalysisContext


class HeuristicProvider:
    """Rule-based provider implementing the :class:`AIProvider` protocol."""

    name = "heuristic"
    model = "rules-v1"

    async def analyze(self, context: AnalysisContext) -> AIInsight:
        result = context.result
        parsed = context.parsed
        strengths = list(result.get("strengths", []))[:5]
        improvements = list(result.get("suggestions", []))[:5]
        has_content = bool(parsed.metadata.word_count)
        confidence = 0.55 if has_content else 0.2
        return AIInsight(
            summary=str(result.get("summary", ""))[:1200],
            strengths=strengths,
            improvements=improvements,
            matched_skills=list(result.get("matched_skills", []))[:30],
            missing_skills=list(result.get("missing_skills", []))[:30],
            confidence=round(min(max(confidence, 0.0), 1.0), 2),
            provider=self.name,
            model=self.model,
            degraded=False,
        )
