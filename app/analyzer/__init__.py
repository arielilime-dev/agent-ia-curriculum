"""Resume analysis engine: extraction, parsing, scoring and AI enrichment."""

from app.analyzer.ai import AIProvider, HeuristicProvider, build_ai_provider
from app.analyzer.extractors import (
    SUPPORTED_EXTENSIONS,
    CorruptedDocumentError,
    EmptyDocumentError,
    ExtractionError,
    UnsupportedFormatError,
    extract_text,
    file_extension,
    sanitize_filename,
)
from app.analyzer.parser import ParsedResume, ResumeParser, parse_resume
from app.analyzer.pipeline import AnalysisOutcome, ResumeAnalysisPipeline
from app.analyzer.scoring import score_resume, verdict_for
from app.analyzer.skills import SKILL_CATALOG, SKILLS_BY_NAME, find_skills

__all__ = [
    "AIProvider",
    "AnalysisOutcome",
    "CorruptedDocumentError",
    "EmptyDocumentError",
    "ExtractionError",
    "HeuristicProvider",
    "ParsedResume",
    "ResumeAnalysisPipeline",
    "ResumeParser",
    "SKILL_CATALOG",
    "SKILLS_BY_NAME",
    "SUPPORTED_EXTENSIONS",
    "UnsupportedFormatError",
    "build_ai_provider",
    "extract_text",
    "file_extension",
    "find_skills",
    "parse_resume",
    "sanitize_filename",
    "score_resume",
    "verdict_for",
]
