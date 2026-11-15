"""Resume upload and parsed-profile schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContactSchema(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: dict[str, str] = Field(default_factory=dict)


class EducationSchema(BaseModel):
    degree: str
    institution: str | None = None
    year: str | None = None
    level: int = 0


class ExperienceSchema(BaseModel):
    title: str
    company: str | None = None
    start_date: str | None = Field(default=None, description="YYYY-MM")
    end_date: str | None = Field(default=None, description="YYYY-MM; null when current")
    is_current: bool = False
    description: str = ""
    months: int = 0


class LanguageSchema(BaseModel):
    name: str
    level: str | None = None


class ParsedMetadataSchema(BaseModel):
    word_count: int = 0
    char_count: int = 0
    language: str = "unknown"
    sections_found: list[str] = Field(default_factory=list)
    years_experience: float = 0.0
    education_level: int = 0


class ParsedResumeSchema(BaseModel):
    contact: ContactSchema = Field(default_factory=ContactSchema)
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    education: list[EducationSchema] = Field(default_factory=list)
    experience: list[ExperienceSchema] = Field(default_factory=list)
    languages: list[LanguageSchema] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    metadata: ParsedMetadataSchema = Field(default_factory=ParsedMetadataSchema)


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_filename: str
    content_type: str
    size_bytes: int
    language: str
    word_count: int
    years_experience: float
    education_level: int
    skills: list[str]
    parsed: ParsedResumeSchema
    created_at: datetime
    updated_at: datetime


class ResumeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    language: str
    word_count: int
    years_experience: float
    education_level: int
    skills: list[str]
    created_at: datetime


class ResumeText(BaseModel):
    id: str
    text: str
    word_count: int
