"""AI provider abstraction, prompt building and resilient insight parsing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, runtime_checkable

from app.analyzer.parser import ParsedResume


class AIProviderError(Exception):
    """Raised when an AI provider cannot produce a usable insight."""

    def __init__(self, message: str, *, provider: str | None = None) -> None:
        self.provider = provider
        super().__init__(message)


@dataclass(frozen=True)
class AnalysisContext:
    """Everything an AI provider needs to enrich a deterministic analysis."""

    resume_text: str
    parsed: ParsedResume
    result: dict[str, Any]
    job_description: str | None = None
    job_title: str | None = None


@dataclass(frozen=True)
class AIInsight:
    """Validated, provider-agnostic enrichment returned by the AI layer."""

    summary: str = ""
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    confidence: float = 0.5
    provider: str = "heuristic"
    model: str = "rules-v1"
    degraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "strengths": self.strengths,
            "improvements": self.improvements,
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "confidence": self.confidence,
            "provider": self.provider,
            "model": self.model,
            "degraded": self.degraded,
        }


@runtime_checkable
class AIProvider(Protocol):
    """Structural interface implemented by every provider."""

    name: str
    model: str

    async def analyze(self, context: AnalysisContext) -> AIInsight: ...


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)


def _coerce_string_list(value: Any, *, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, (int, float)):
            item = str(item)
        if not isinstance(item, str):
            continue
        cleaned = " ".join(item.split())
        if cleaned and cleaned not in items:
            items.append(cleaned[:400])
        if len(items) >= limit:
            break
    return items


def parse_insight_payload(
    content: str,
    *,
    provider: str,
    model: str,
    degraded: bool = False,
) -> AIInsight:
    """Parse and validate the JSON object returned by an LLM.

    Tolerates markdown fences and surrounding prose, rejects non-object
    payloads and clamps every field to safe sizes.
    """
    if not content or not content.strip():
        raise AIProviderError("The AI provider returned an empty response", provider=provider)

    candidate = content.strip()
    fenced = _FENCE_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AIProviderError("The AI provider did not return a JSON object", provider=provider)

    try:
        payload = json.loads(candidate[start : end + 1])
    except (ValueError, TypeError) as exc:
        raise AIProviderError("The AI provider returned invalid JSON", provider=provider) from exc
    if not isinstance(payload, dict):
        raise AIProviderError("The AI provider returned an invalid payload", provider=provider)

    summary = payload.get("summary")
    summary = " ".join(summary.split())[:1200] if isinstance(summary, str) else ""

    confidence_raw = payload.get("confidence", 0.5)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    return AIInsight(
        summary=summary,
        strengths=_coerce_string_list(payload.get("strengths"), limit=6),
        improvements=_coerce_string_list(payload.get("improvements"), limit=6),
        matched_skills=_coerce_string_list(payload.get("matched_skills"), limit=30),
        missing_skills=_coerce_string_list(payload.get("missing_skills"), limit=30),
        confidence=round(confidence, 2),
        provider=provider,
        model=model,
        degraded=degraded,
    )


def mark_degraded(insight: AIInsight, *, provider: str | None = None) -> AIInsight:
    """Return a copy of *insight* flagged as a degraded (fallback) result."""
    return replace(insight, degraded=True, provider=provider or insight.provider)
