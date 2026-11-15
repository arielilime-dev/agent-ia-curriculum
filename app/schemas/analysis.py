"""Analysis request/response and dashboard schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnalysisCreate(BaseModel):
    resume_id: str = Field(min_length=8, max_length=36)
    job_title: str | None = Field(default=None, max_length=200)
    job_description: str | None = Field(default=None, max_length=20_000)

    @field_validator("job_title", "job_description")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class DimensionScore(BaseModel):
    label: str
    score: float
    weight: float
    weighted: float
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)


class AtsCheck(BaseModel):
    id: str
    label: str
    passed: bool
    hint: str


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    resume_id: str
    job_title: str | None
    job_description: str | None
    overall_score: float
    verdict: str
    breakdown: dict[str, DimensionScore]
    matched_skills: list[str]
    missing_skills: list[str]
    matched_keywords: list[str]
    missing_keywords: list[str]
    strengths: list[str]
    suggestions: list[str]
    ats_checks: list[AtsCheck]
    summary: str
    ai_provider: str
    ai_model: str
    ai_degraded: bool
    duration_ms: int
    created_at: datetime


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    resume_id: str
    job_title: str | None
    overall_score: float
    verdict: str
    ai_provider: str
    ai_degraded: bool
    created_at: datetime


class SkillCount(BaseModel):
    skill: str
    count: int


class DashboardStats(BaseModel):
    total_resumes: int
    total_analyses: int
    average_score: float | None = None
    best_score: float | None = None
    top_skills: list[SkillCount] = Field(default_factory=list)
    recent_analyses: list[AnalysisSummary] = Field(default_factory=list)
