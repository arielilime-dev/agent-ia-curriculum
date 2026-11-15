"""Education level taxonomy and keyword detection (PT-BR and English)."""

from __future__ import annotations

from enum import IntEnum

from app.analyzer.text import normalize


class EducationLevel(IntEnum):
    """Ordered education levels used for scoring."""

    NONE = 0
    FUNDAMENTAL = 1
    MEDIO = 2
    TECNICO = 3
    SUPERIOR = 4
    POS_GRADUACAO = 5
    MESTRADO = 6
    DOUTORADO = 7


EDUCATION_LABELS: dict[int, str] = {
    EducationLevel.NONE: "Não informado",
    EducationLevel.FUNDAMENTAL: "Ensino fundamental",
    EducationLevel.MEDIO: "Ensino médio",
    EducationLevel.TECNICO: "Ensino técnico",
    EducationLevel.SUPERIOR: "Ensino superior",
    EducationLevel.POS_GRADUACAO: "Pós-graduação / MBA",
    EducationLevel.MESTRADO: "Mestrado",
    EducationLevel.DOUTORADO: "Doutorado",
}

# Checked from the highest level down so that "pós-graduação" does not match
# the "graduação" keyword and "tecnólogo" does not match "técnico".
_LEVEL_KEYWORDS: tuple[tuple[EducationLevel, tuple[str, ...]], ...] = (
    (
        EducationLevel.DOUTORADO,
        ("doutorado", "doutoranda", "doutorando", "phd", "ph.d", "doctorate", "doctor of"),
    ),
    (
        EducationLevel.MESTRADO,
        ("mestrado", "mestranda", "mestrando", "master of", "master in", "msc", "m.sc"),
    ),
    (
        EducationLevel.POS_GRADUACAO,
        (
            "pos graduacao",
            "pos-graduacao",
            "posgraduacao",
            "especializacao",
            "especialista em",
            "mba",
            "postgraduate",
            "post graduate",
            "specialization",
        ),
    ),
    (
        EducationLevel.SUPERIOR,
        (
            "ensino superior",
            "superior completo",
            "superior incompleto",
            "graduacao",
            "graduando",
            "graduada",
            "graduado",
            "bacharelado",
            "bacharel",
            "licenciatura",
            "tecnologo",
            "tecnologa",
            "bachelor",
            "undergraduate",
            "university degree",
            "college degree",
            "degree in",
            "computer science",
        ),
    ),
    (
        EducationLevel.TECNICO,
        ("ensino tecnico", "curso tecnico", "tecnico em", "technical school", "technical degree"),
    ),
    (
        EducationLevel.MEDIO,
        ("ensino medio", "medio completo", "colegial", "high school", "secondary school"),
    ),
    (EducationLevel.FUNDAMENTAL, ("ensino fundamental", "fundamental completo")),
)


def detect_education_level(text: str) -> EducationLevel:
    """Infer the highest education level mentioned in *text*."""
    normalized = normalize(text)
    if not normalized:
        return EducationLevel.NONE
    for level, keywords in _LEVEL_KEYWORDS:
        for keyword in keywords:
            if " " in keyword or "-" in keyword:
                if keyword in normalized:
                    return level
            elif keyword in normalized.split() or keyword in normalized:
                # Substring matching is safe for these distinctive words.
                return level
    return EducationLevel.NONE


def education_label(level: int) -> str:
    """Return the Portuguese label for *level* (clamped to the valid range)."""
    try:
        return EDUCATION_LABELS.get(int(level), EDUCATION_LABELS[EducationLevel.NONE])
    except (TypeError, ValueError):
        return EDUCATION_LABELS[EducationLevel.NONE]
