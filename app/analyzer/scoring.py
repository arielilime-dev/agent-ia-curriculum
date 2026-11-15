"""Deterministic resume-to-job scoring engine.

Five weighted dimensions produce a 0-100 score:

======================  ======  ==========================================
Dimension               Weight  Signal
======================  ======  ==========================================
skills                  0.40    required skills covered by the resume
experience              0.25    years of experience vs. requirement
education               0.10    highest degree vs. requirement
keywords                0.15    job-description keyword coverage / richness
ats                     0.10    structural checks (contact, length, sections)
======================  ======  ==========================================

Without a job description the "keywords" dimension falls back to content
quality (action verbs, quantified achievements, professional summary).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.analyzer.education import EducationLevel, detect_education_level, education_label
from app.analyzer.parser import ParsedResume
from app.analyzer.skills import categorize, find_skills, technical_skills
from app.analyzer.text import (
    count_action_verbs,
    count_quantified_achievements,
    extract_keywords,
    keyword_present,
    normalize,
    tokenize,
)

WEIGHTS: dict[str, float] = {
    "skills": 0.40,
    "experience": 0.25,
    "education": 0.10,
    "keywords": 0.15,
    "ats": 0.10,
}

DIMENSION_LABELS: dict[str, str] = {
    "skills": "Competências",
    "experience": "Experiência",
    "education": "Formação",
    "keywords": "Palavras-chave",
    "ats": "Compatibilidade com ATS",
}

VERDICT_LABELS: dict[str, str] = {
    "excellent": "Excelente",
    "strong": "Forte",
    "fair": "Razoável",
    "weak": "Fraco",
}

_EDUCATION_SCORE: dict[int, float] = {
    0: 10.0,
    1: 25.0,
    2: 45.0,
    3: 65.0,
    4: 85.0,
    5: 92.0,
    6: 97.0,
    7: 100.0,
}

_REQUIRED_YEARS_RE = re.compile(r"(\d{1,2})\s*(?:\+|mais)?\s*(?:anos?|years?)\b")


def verdict_for(score: float) -> str:
    """Map a numeric score to a stable verdict code."""
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "strong"
    if score >= 55:
        return "fair"
    return "weak"


def extract_required_years(job_description: str | None) -> int | None:
    """Extract the highest ``N anos`` / ``N years`` requirement from a job description."""
    if not job_description:
        return None
    values: list[int] = []
    for match in _REQUIRED_YEARS_RE.finditer(normalize(job_description)):
        value = int(match.group(1))
        if 1 <= value <= 40:
            values.append(value)
    return max(values) if values else None


def extract_required_education(job_description: str | None) -> EducationLevel:
    """Infer the education level required by a job description."""
    if not job_description:
        return EducationLevel.NONE
    return detect_education_level(job_description)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _general_skills_score(skill_names: list[str]) -> tuple[float, dict[str, Any]]:
    technical = technical_skills(skill_names)
    categories = {categorize(name) for name in technical}
    breadth = min(len(technical) / 12, 1.0) * 70
    diversity = min(len(categories) / 5, 1.0) * 30
    score = round(breadth + diversity, 1)
    return score, {"technical_skills": len(technical), "categories": sorted(categories)}


def _ats_checks(parsed: ParsedResume) -> list[dict[str, Any]]:
    words = parsed.metadata.word_count
    checks: list[dict[str, Any]] = [
        {
            "id": "email",
            "label": "E-mail de contato",
            "passed": bool(parsed.contact.email),
            "hint": "Inclua um e-mail profissional no cabeçalho do currículo.",
        },
        {
            "id": "phone",
            "label": "Telefone de contato",
            "passed": bool(parsed.contact.phone),
            "hint": "Inclua um telefone com DDD para contato rápido.",
        },
        {
            "id": "length",
            "label": "Extensão adequada",
            "passed": 200 <= words <= 2000,
            "hint": "Busque entre 200 e 2.000 palavras (ideal: 400 a 800).",
        },
        {
            "id": "experience",
            "label": "Experiência profissional",
            "passed": bool(parsed.experience),
            "hint": "Descreva suas experiências com cargo, empresa e período.",
        },
        {
            "id": "education",
            "label": "Formação acadêmica",
            "passed": bool(parsed.education),
            "hint": "Inclua sua formação, instituição e ano de conclusão.",
        },
        {
            "id": "skills",
            "label": "Competências técnicas",
            "passed": len(parsed.skills) >= 3,
            "hint": "Liste ao menos três competências relevantes para a vaga.",
        },
        {
            "id": "summary",
            "label": "Resumo profissional",
            "passed": bool(parsed.summary),
            "hint": "Adicione um resumo de 2 a 4 linhas com seu posicionamento.",
        },
        {
            "id": "links",
            "label": "Perfil profissional online",
            "passed": bool(parsed.contact.links),
            "hint": "Adicione LinkedIn ou GitHub para dar credibilidade ao perfil.",
        },
    ]
    return checks


def _build_summary(
    parsed: ParsedResume,
    *,
    overall: float,
    verdict: str,
    has_job: bool,
    coverage: float | None,
) -> str:
    years = parsed.metadata.years_experience
    skills_count = len(parsed.skills)
    level_label = education_label(parsed.metadata.education_level)
    if years <= 0 and skills_count == 0 and not parsed.experience:
        return (
            "Não foi possível identificar informações suficientes no currículo. "
            "Verifique se o arquivo contém texto selecionável e inclua experiências, "
            "formação e competências."
        )

    parts = []
    if years > 0:
        parts.append(f"{years:g} anos de experiência profissional")
    else:
        parts.append("experiência profissional inicial")
    if skills_count:
        top = ", ".join(parsed.skills[:5])
        parts.append(f"{skills_count} competências identificadas ({top})")
    if parsed.metadata.education_level:
        parts.append(f"formação: {level_label.lower()}")
    summary = "Perfil com " + "; ".join(parts) + "."
    if has_job and coverage is not None:
        summary += f" Aderência às competências da vaga: {coverage:.0f}%."
    summary += f" Score geral {overall:g}/100 ({VERDICT_LABELS[verdict]})."
    return summary


def score_resume(
    parsed: ParsedResume,
    *,
    job_description: str | None = None,
    job_title: str | None = None,
    resume_text: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Score *parsed* (optionally against a job description) and explain why."""
    del now, job_title  # reserved for future temporal/role-aware heuristics
    text = resume_text or " ".join(
        [
            parsed.summary,
            " ".join(parsed.skills),
            " ".join(
                f"{entry.title} {entry.company or ''} {entry.description}"
                for entry in parsed.experience
            ),
            " ".join(f"{entry.degree} {entry.institution or ''}" for entry in parsed.education),
        ]
    )
    jd = (job_description or "").strip()
    has_job = bool(jd)

    candidate_skills = set(parsed.skills)
    required_skills = find_skills(jd) if has_job else []
    matched_skills = [skill for skill in required_skills if skill in candidate_skills]
    missing_skills = [skill for skill in required_skills if skill not in candidate_skills]
    coverage: float | None = None

    # -- Skills --------------------------------------------------------------
    if required_skills:
        coverage = len(matched_skills) / len(required_skills)
        skills_score = round(coverage * 100, 1)
        skills_details: dict[str, Any] = {
            "required_skills": required_skills[:20],
            "matched_skills": matched_skills,
            "missing_skills": missing_skills[:20],
            "coverage": round(coverage, 3),
        }
    else:
        skills_score, skills_details = _general_skills_score(parsed.skills)

    # -- Experience ----------------------------------------------------------
    years = parsed.metadata.years_experience
    required_years = extract_required_years(jd) if has_job else None
    if required_years:
        experience_score = round(min(years / required_years, 1.0) * 100, 1)
        experience_reason = f"{years:g} de {required_years} anos exigidos"
    else:
        experience_score = round(min(years / 8, 1.0) * 100, 1)
        if years == 0 and parsed.experience:
            experience_score = 20.0
        experience_reason = f"{years:g} anos de experiência identificados"

    # -- Education -----------------------------------------------------------
    candidate_level = parsed.metadata.education_level
    required_level = int(extract_required_education(jd)) if has_job else 0
    if required_level:
        if candidate_level >= required_level:
            education_score = 100.0
        else:
            education_score = max(0.0, 100.0 - 25.0 * (required_level - candidate_level))
        education_reason = (
            f"{education_label(candidate_level)} para exigência de "
            f"{education_label(required_level)}"
        )
    else:
        education_score = _EDUCATION_SCORE.get(candidate_level, 10.0)
        education_reason = education_label(candidate_level)

    # -- Keywords / content quality -----------------------------------------
    matched_keywords: list[str] = []
    missing_keywords: list[str] = []
    if has_job:
        job_keywords = extract_keywords(jd, limit=25, min_length=4)
        resume_tokens = set(tokenize(text))
        normalized_resume = normalize(text)
        matched_keywords = [
            keyword
            for keyword in job_keywords
            if keyword_present(keyword, resume_tokens, normalized_resume)
        ]
        missing_keywords = [keyword for keyword in job_keywords if keyword not in matched_keywords]
        if job_keywords:
            keyword_score = round(len(matched_keywords) / len(job_keywords) * 100, 1)
        else:
            keyword_score = 0.0
        keyword_details: dict[str, Any] = {
            "job_keywords": job_keywords[:20],
            "matched_keywords": matched_keywords[:20],
            "missing_keywords": missing_keywords[:20],
            "coverage": round(len(matched_keywords) / len(job_keywords), 3)
            if job_keywords
            else 0.0,
        }
    else:
        experience_text = " ".join(
            f"{entry.title} {entry.description}" for entry in parsed.experience
        )
        verbs = count_action_verbs(experience_text)
        metrics = count_quantified_achievements(text)
        verb_score = min(verbs / 6, 1.0) * 40
        metric_score = min(metrics / 4, 1.0) * 30
        summary_score = 30.0 if parsed.summary else 0.0
        keyword_score = round(verb_score + metric_score + summary_score, 1)
        keyword_details = {
            "action_verbs": verbs,
            "quantified_achievements": metrics,
            "has_summary": bool(parsed.summary),
        }

    # -- ATS -----------------------------------------------------------------
    ats_checks = _ats_checks(parsed)
    passed_checks = [check for check in ats_checks if check["passed"]]
    ats_score = round(len(passed_checks) / len(ats_checks) * 100, 1)
    ats_details = {
        "passed": len(passed_checks),
        "total": len(ats_checks),
        "failed": [check["id"] for check in ats_checks if not check["passed"]],
    }

    scores = {
        "skills": skills_score,
        "experience": experience_score,
        "education": education_score,
        "keywords": keyword_score,
        "ats": ats_score,
    }
    breakdown: dict[str, dict[str, Any]] = {}
    technical_count = skills_details.get("technical_skills", 0)
    keyword_total = len(missing_keywords) + len(matched_keywords)
    reasons = {
        "skills": (
            f"{len(matched_skills)} de {len(required_skills)} competências da vaga"
            if required_skills
            else f"{technical_count} competências técnicas identificadas"
        ),
        "experience": experience_reason,
        "education": education_reason,
        "keywords": (
            f"{len(matched_keywords)} de {keyword_total} palavras-chave da vaga"
            if has_job
            else "qualidade do conteúdo (verbos de ação, métricas e resumo)"
        ),
        "ats": f"{len(passed_checks)} de {len(ats_checks)} verificações aprovadas",
    }
    for dimension, score in scores.items():
        breakdown[dimension] = {
            "label": DIMENSION_LABELS[dimension],
            "score": round(score, 1),
            "weight": WEIGHTS[dimension],
            "weighted": round(score * WEIGHTS[dimension], 2),
            "reason": reasons[dimension],
            "details": {
                "skills": skills_details,
                "experience": {
                    "years": years,
                    "required_years": required_years,
                },
                "education": {
                    "level": candidate_level,
                    "label": education_label(candidate_level),
                    "required_level": required_level or None,
                    "required_label": education_label(required_level) if required_level else None,
                },
                "keywords": keyword_details,
                "ats": ats_details,
            }[dimension],
        }

    overall = round(sum(scores[dimension] * WEIGHTS[dimension] for dimension in WEIGHTS), 1)
    overall = max(0.0, min(100.0, overall))
    verdict = verdict_for(overall)

    # -- Narrative -----------------------------------------------------------
    strengths: list[str] = []
    if matched_skills:
        strengths.append(
            f"Atende {len(matched_skills)} competência(s) exigida(s): "
            + ", ".join(matched_skills[:6])
        )
    if years >= 5:
        strengths.append(f"{years:g} anos de experiência profissional comprovada")
    elif years > 0:
        strengths.append(f"{years:g} anos de experiência profissional")
    if candidate_level >= EducationLevel.SUPERIOR:
        strengths.append(f"Formação acadêmica: {education_label(candidate_level).lower()}")
    if len(passed_checks) >= 7:
        strengths.append("Currículo bem estruturado para sistemas de triagem (ATS)")
    if len(parsed.languages) >= 2:
        strengths.append(
            "Perfil multilíngue: " + ", ".join(entry.name for entry in parsed.languages)
        )
    if parsed.certifications:
        strengths.append(f"{len(parsed.certifications)} certificação(ões)/curso(s) listados")
    if len(parsed.skills) >= 8:
        strengths.append(f"Portfólio técnico amplo com {len(parsed.skills)} competências mapeadas")

    suggestions: list[str] = []
    if missing_skills:
        suggestions.append(
            "Evidencie as competências ausentes: " + ", ".join(missing_skills[:6]) + "."
        )
    if required_years and years < required_years:
        suggestions.append(
            f"A vaga pede {required_years} anos de experiência e o currículo evidencia "
            f"{years:g}. Destaque projetos equivalentes e resultados mensuráveis."
        )
    if required_level and candidate_level < required_level:
        suggestions.append(
            f"A vaga exige {education_label(required_level).lower()}; "
            f"o currículo indica {education_label(candidate_level).lower()}."
        )
    if not parsed.contact.email:
        suggestions.append("Inclua um e-mail profissional no cabeçalho do currículo.")
    if not parsed.contact.phone:
        suggestions.append("Inclua um telefone com DDD para contato.")
    if parsed.metadata.word_count < 200:
        suggestions.append(
            "O currículo está curto: detalhe atividades, tecnologias e resultados "
            "(mínimo recomendado de 200 palavras)."
        )
    elif parsed.metadata.word_count > 2000:
        suggestions.append("O currículo está longo: priorize as experiências mais relevantes.")
    if not parsed.experience:
        suggestions.append("Inclua experiências com cargo, empresa, período e principais entregas.")
    if not parsed.summary:
        suggestions.append("Adicione um resumo profissional de 2 a 4 linhas no topo do currículo.")
    if count_quantified_achievements(text) < 2:
        suggestions.append(
            "Quantifique resultados (percentuais, valores, volume ou tempo economizado)."
        )
    if (
        has_job
        and missing_keywords
        and len(matched_keywords) / max(len(matched_keywords) + len(missing_keywords), 1) < 0.6
    ):
        suggestions.append(
            "Aproxime o vocabulário do currículo da vaga: " + ", ".join(missing_keywords[:6]) + "."
        )
    if not parsed.contact.links:
        suggestions.append("Adicione LinkedIn ou GitHub ao cabeçalho.")

    return {
        "overall_score": overall,
        "verdict": verdict,
        "breakdown": breakdown,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "strengths": _dedupe(strengths)[:6],
        "suggestions": _dedupe(suggestions)[:8],
        "ats_checks": ats_checks,
        "summary": _build_summary(
            parsed,
            overall=overall,
            verdict=verdict,
            has_job=has_job,
            coverage=coverage,
        ),
        "metadata": {
            "years_experience": years,
            "education_level": candidate_level,
            "education_label": education_label(candidate_level),
            "word_count": parsed.metadata.word_count,
            "required_years": required_years,
            "required_education_level": required_level or None,
            "required_education_label": education_label(required_level) if required_level else None,
            "required_skills_count": len(required_skills),
            "has_job_description": has_job,
            "language": parsed.metadata.language,
        },
    }
