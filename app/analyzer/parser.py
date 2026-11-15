"""Rule-based resume parser: turns raw text into a structured profile.

The parser is intentionally heuristic but conservative: it never raises on
unexpected input, returns empty structures when information is missing, and
records what it found in ``metadata`` so the scoring layer can react.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.analyzer.education import EducationLevel, detect_education_level
from app.analyzer.skills import find_skills
from app.analyzer.text import (
    count_words,
    detect_language,
    extract_emails,
    extract_phones,
    extract_urls,
    normalize,
    strip_accents,
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ContactInfo:
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: dict[str, str] = field(default_factory=dict)


@dataclass
class EducationEntry:
    degree: str
    institution: str | None = None
    year: str | None = None
    level: int = int(EducationLevel.NONE)


@dataclass
class ExperienceEntry:
    title: str
    company: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str = ""
    months: int = 0


@dataclass
class LanguageEntry:
    name: str
    level: str | None = None


@dataclass
class ResumeMetadata:
    word_count: int = 0
    char_count: int = 0
    language: str = "unknown"
    sections_found: list[str] = field(default_factory=list)
    years_experience: float = 0.0
    education_level: int = int(EducationLevel.NONE)


@dataclass
class ParsedResume:
    contact: ContactInfo = field(default_factory=ContactInfo)
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    education: list[EducationEntry] = field(default_factory=list)
    experience: list[ExperienceEntry] = field(default_factory=list)
    languages: list[LanguageEntry] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    metadata: ResumeMetadata = field(default_factory=ResumeMetadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contact": asdict(self.contact),
            "summary": self.summary,
            "skills": list(self.skills),
            "education": [asdict(entry) for entry in self.education],
            "experience": [asdict(entry) for entry in self.experience],
            "languages": [asdict(entry) for entry in self.languages],
            "certifications": list(self.certifications),
            "projects": list(self.projects),
            "metadata": asdict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

SECTION_ALIASES: dict[str, frozenset[str]] = {
    "summary": frozenset(
        {
            "resumo",
            "resumo profissional",
            "resumo de carreira",
            "perfil",
            "perfil profissional",
            "objetivo",
            "objetivo profissional",
            "sobre",
            "sobre mim",
            "about",
            "about me",
            "summary",
            "professional summary",
            "profile",
            "profile summary",
            "objective",
            "career objective",
        }
    ),
    "experience": frozenset(
        {
            "experiencia",
            "experiencias",
            "experiencia profissional",
            "experiencias profissionais",
            "experiencia de trabalho",
            "historico profissional",
            "trajetoria profissional",
            "atuacao profissional",
            "work experience",
            "professional experience",
            "experience",
            "employment",
            "employment history",
            "work history",
            "career history",
        }
    ),
    "education": frozenset(
        {
            "formacao",
            "formacao academica",
            "formacao educacional",
            "educacao",
            "escolaridade",
            "qualificacoes academicas",
            "education",
            "academic background",
            "educational background",
            "academic qualifications",
        }
    ),
    "skills": frozenset(
        {
            "habilidades",
            "habilidades tecnicas",
            "habilidades e competencias",
            "competencias",
            "competencias tecnicas",
            "conhecimentos",
            "conhecimentos tecnicos",
            "conhecimento tecnico",
            "tecnologias",
            "ferramentas",
            "stack",
            "tech stack",
            "skills",
            "technical skills",
            "technologies",
            "core competencies",
            "competencies",
            "expertise",
        }
    ),
    "languages": frozenset(
        {
            "idiomas",
            "idioma",
            "linguas",
            "languages",
            "language skills",
            "foreign languages",
        }
    ),
    "certifications": frozenset(
        {
            "certificacoes",
            "certificacoes e cursos",
            "certificados",
            "cursos",
            "cursos e certificacoes",
            "cursos complementares",
            "qualificacoes",
            "certifications",
            "certificates",
            "courses",
            "licenses and certifications",
            "licenses & certifications",
        }
    ),
    "projects": frozenset(
        {
            "projetos",
            "projetos pessoais",
            "projetos profissionais",
            "portfolio",
            "projects",
            "personal projects",
            "side projects",
        }
    ),
    "additional": frozenset(
        {
            "informacoes adicionais",
            "informacoes complementares",
            "outras informacoes",
            "additional information",
            "additional info",
            "extras",
        }
    ),
}

_ALIAS_TO_SECTION: dict[str, str] = {
    alias: section for section, aliases in SECTION_ALIASES.items() for alias in aliases
}

_BULLET_RE = re.compile(r"^\s*(?:[-•*·▪◦‣]|\d{1,2}[.)])\s+")
_HEADER_SPLIT_RE = re.compile(r"\s*(?:[—–|]|\s-\s|@|\bat\b|\bna\b|,)\s*", re.IGNORECASE)
_INSTITUTION_HINTS = (
    "universidade",
    "universidad",
    "university",
    "faculdade",
    "faculty",
    "instituto",
    "institute",
    "centro universitario",
    "escola",
    "school",
    "college",
    "academy",
    "academia",
    "senac",
    "senai",
    "fiocruz",
    "usp",
    "unicamp",
    "ufrj",
    "ufmg",
)
_JOB_TITLE_KEYWORDS = (
    "desenvolvedor",
    "desenvolvedora",
    "developer",
    "engenheiro",
    "engenheira",
    "engineer",
    "analista",
    "analyst",
    "gerente",
    "manager",
    "coordenador",
    "coordenadora",
    "coordinator",
    "diretor",
    "diretora",
    "director",
    "especialista",
    "specialist",
    "consultor",
    "consultora",
    "consultant",
    "arquiteto",
    "arquiteta",
    "architect",
    "designer",
    "estagiario",
    "estagiaria",
    "intern",
    "professor",
    "professora",
    "teacher",
    "cientista",
    "scientist",
    "tech lead",
    "lider",
    "lead",
    "supervisor",
    "assistente",
    "assistant",
    "tecnico",
    "tecnica",
    "administrador",
    "administrator",
    "product owner",
    "scrum master",
    "devops",
    "sre",
    "qa",
)
_COMPANY_HINTS = (
    "ltda",
    "s.a",
    "s/a",
    "inc",
    "corp",
    "llc",
    "group",
    "grupo",
    "bank",
    "banco",
    "company",
    "companhia",
    "empresa",
    "technologies",
    "technology",
    "solutions",
    "systems",
    "consulting",
    "consultoria",
    "services",
    "servicos",
    "labs",
    "software",
    "digital",
    "tech",
    "universidade",
    "instituto",
    "fundacao",
    "hospital",
    "escola",
    "sa",
)

# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTHS = {
    "jan": 1,
    "fev": 2,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "aug": 8,
    "set": 9,
    "sep": 9,
    "out": 10,
    "oct": 10,
    "nov": 11,
    "dez": 12,
    "dec": 12,
}

_DATE_CANDIDATE_RE = re.compile(
    r"(?P<md>\d{1,2})\s*/\s*(?P<my>(?:19|20)\d{2})"
    r"|(?P<mn>jan(?:eiro)?|fev(?:ereiro)?|feb(?:ruary)?|mar(?:co|ch)?|abr(?:il)?|apr(?:il)?"
    r"|mai(?:o)?|may|jun(?:ho|e)?|jul(?:ho|y)?|ago(?:sto)?|aug(?:ust)?|set(?:embro)?"
    r"|sep(?:tember)?|out(?:ubro)?|oct(?:ober)?|nov(?:embro|ember)?|dez(?:embro)?|dec(?:ember)?)"
    r"\.?\s*(?:de\s+|/\s*)?(?P<ny>(?:19|20)\d{2})"
    r"|(?P<y>(?:19|20)\d{2})",
    re.IGNORECASE,
)
_PRESENT_RE = re.compile(
    r"\b(?:atual|atualmente|presente|present|current|currently|hoje|momento|now)\b"
)
_DATE_NORMALIZE_RE = re.compile(r"[^a-z0-9/.\-\s]")
_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_YEAR_ONLY_RE = re.compile(r"^\s*(?:(?:19|20)\d{2}\s*[-–—/]\s*(?:19|20)\d{2}|(?:19|20)\d{2})\s*$")


def _normalize_dates(value: str) -> str:
    text = strip_accents(value).lower()
    text = text.replace("–", "-").replace("—", "-")
    text = _DATE_NORMALIZE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find_dates(value: str) -> list[tuple[int, int]]:
    """Return ``(year, month)`` pairs found in *value*, preserving order."""
    text = _normalize_dates(value)
    dates: list[tuple[int, int]] = []
    for match in _DATE_CANDIDATE_RE.finditer(text):
        if match.group("md"):
            month = int(match.group("md"))
            year = int(match.group("my"))
        elif match.group("mn"):
            month = _MONTHS.get(match.group("mn")[:3].lower(), 0)
            year = int(match.group("ny"))
        else:
            month = 1
            year = int(match.group("y"))
        if not 1 <= month <= 12 or not 1900 <= year <= 2100:
            continue
        entry = (year, month)
        if not dates or dates[-1] != entry:
            dates.append(entry)
    return dates


def _is_present(value: str) -> bool:
    return bool(_PRESENT_RE.search(_normalize_dates(value)))


def _month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def _format_month(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _split_period(line: str, now: datetime) -> tuple[tuple[int, int], tuple[int, int], bool] | None:
    dates = _find_dates(line)
    if not dates:
        return None
    present = _is_present(line)
    if len(dates) >= 2:
        return dates[0], dates[1], False
    if present:
        return dates[0], (now.year, now.month), True
    return dates[0], dates[0], False


def _total_months(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    ordered = sorted((start, end) for start, end in intervals if end >= start)
    merged: list[list[int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return sum(end - start + 1 for start, end in merged)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _clean_bullet(line: str) -> str:
    return _BULLET_RE.sub("", line).strip()


def _is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _strip_dates(line: str) -> str:
    cleaned = _DATE_CANDIDATE_RE.sub(" ", _normalize_dates(line))
    cleaned = _PRESENT_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s*[-–—|]\s*", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" -–—|,")


def detect_section_header(line: str) -> str | None:
    """Map a line to a canonical section name when it is a heading."""
    if not line or len(line) > 70:
        return None
    candidate = line.strip().strip(":.-–—•* ").lower()
    candidate = re.sub(r"^\d{1,2}[.)]\s*", "", candidate)
    key = normalize(candidate)
    if not key or len(key) > 60:
        return None
    return _ALIAS_TO_SECTION.get(key)


def split_sections(text: str) -> dict[str, list[str]]:
    """Split *text* into canonical sections, keeping the preamble under ``header``."""
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            if current != "header" and sections[current]:
                sections[current].append("")
            continue
        section = detect_section_header(line)
        if section:
            current = section
            sections.setdefault(section, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


# ---------------------------------------------------------------------------
# Contact extraction
# ---------------------------------------------------------------------------


def _looks_like_job_title(text: str) -> bool:
    normalized = normalize(text)
    return any(keyword in normalized for keyword in _JOB_TITLE_KEYWORDS)


def _looks_like_company(text: str) -> bool:
    normalized = normalize(text)
    return any(keyword in normalized for keyword in _COMPANY_HINTS)


_NAME_CONNECTORS = frozenset({"da", "de", "do", "das", "dos", "e", "di", "du", "del", "van", "von"})


def _looks_like_name(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 70:
        return False
    if any(char.isdigit() for char in line):
        return False
    lowered = line.lower()
    if any(token in lowered for token in ("@", "http", "www.", "linkedin", "github", "curriculo")):
        return False
    if "|" in line or ":" in line or "," in line or ";" in line:
        return False
    if detect_section_header(line):
        return False
    words = line.split()
    if not 2 <= len(words) <= 5:
        return False
    if _looks_like_job_title(line):
        return False
    for word in words:
        if not word or not word[0].isalpha():
            return False
        if word.lower() in _NAME_CONNECTORS:
            continue
        if not word[0].isupper():
            return False
    return True


_LOCATION_RE = re.compile(
    r"^[A-Za-zÀ-ÿ.'\s]+?[\s]*[-–,][\s]*(?:[A-Z]{2}|Brasil|Brazil|Portugal|Remoto|Remote|Híbrido|Hibrido)$"
)
_REMOTE_RE = re.compile(r"^(?:remoto|remote|home office|hibrido|híbrido)$", re.IGNORECASE)


def _extract_location(lines: list[str]) -> str | None:
    for line in lines:
        for segment in re.split(r"\s*[|•·]\s*", line):
            segment = segment.strip(" .;,")
            if not segment or "@" in segment:
                continue
            if _LOCATION_RE.match(segment) or _REMOTE_RE.match(segment):
                return segment
    return None


def _extract_name(header_lines: list[str], fallback_lines: list[str]) -> str | None:
    for line in header_lines[:10]:
        if _looks_like_name(line):
            return " ".join(line.split())
    for line in fallback_lines[:5]:
        if _looks_like_name(line):
            return " ".join(line.split())
    return None


def _parse_contact(text: str, header_lines: list[str]) -> ContactInfo:
    emails = extract_emails(text)
    phones = extract_phones(text)
    links = extract_urls(text)
    location_source = header_lines or [line for line in text.splitlines() if line.strip()][:10]
    fallback_lines = [
        line
        for line in text.splitlines()
        if line.strip() and not detect_section_header(line.strip())
    ]
    return ContactInfo(
        full_name=_extract_name(header_lines, fallback_lines),
        email=emails[0] if emails else None,
        phone=phones[0] if phones else None,
        location=_extract_location(location_source),
        links=links,
    )


# ---------------------------------------------------------------------------
# Experience
# ---------------------------------------------------------------------------


def _split_header(header: str) -> tuple[str, str | None]:
    """Split ``Company — Title`` (or ``Title | Company``) heuristically."""
    cleaned = header.strip().strip(" -–—|,;")
    if not cleaned:
        return "", None
    parts = [part.strip() for part in _HEADER_SPLIT_RE.split(cleaned) if part.strip()]
    if not parts:
        return "", None
    if len(parts) == 1:
        return parts[0][:160], None

    title_index = next((i for i, part in enumerate(parts) if _looks_like_job_title(part)), None)
    if title_index is None:
        company_index = next((i for i, part in enumerate(parts) if _looks_like_company(part)), None)
        if company_index is not None and company_index != 0:
            title_index = 0
        elif company_index == 0:
            title_index = 1
        else:
            title_index = 0
    title = parts[title_index][:160]
    company_parts = [part for i, part in enumerate(parts) if i != title_index]
    company = " ".join(company_parts)[:160] if company_parts else None
    return title, company or None


def _parse_experience(lines: list[str], now: datetime) -> tuple[list[ExperienceEntry], float]:
    date_indices = [index for index, line in enumerate(lines) if _find_dates(line)]
    if not date_indices:
        entries = [
            ExperienceEntry(title=_clean_bullet(line)[:160], months=0)
            for line in lines
            if line.strip() and not _is_bullet(line)
        ][:10]
        return entries, 0.0

    header_indices: set[int] = set()
    for index in date_indices:
        if index - 1 >= 0 and not _is_bullet(lines[index - 1]) and lines[index - 1].strip():
            header_indices.add(index - 1)
        elif index - 1 >= 0 and _is_bullet(lines[index - 1]):
            # A bullet immediately before a date is usually a description line.
            continue

    entries: list[ExperienceEntry] = []
    intervals: list[tuple[int, int]] = []
    for position, index in enumerate(date_indices):
        date_line = lines[index]
        header = ""
        if index - 1 in header_indices:
            header = lines[index - 1].strip()
        if header:
            title, company = _split_header(header)
        else:
            title, company = _split_header(_strip_dates(date_line))
        if not title:
            title = "Experiência profissional"
        period = _split_period(date_line, now)

        next_date_index = (
            date_indices[position + 1] if position + 1 < len(date_indices) else len(lines)
        )
        description_end = next_date_index
        if next_date_index - 1 in header_indices and next_date_index - 1 > index:
            description_end = next_date_index - 1
        description_lines: list[str] = []
        for line_index in range(index + 1, description_end):
            if line_index in header_indices or line_index in date_indices:
                continue
            value = _clean_bullet(lines[line_index])
            if value:
                description_lines.append(value)
        description = " ".join(description_lines)[:800]

        start_date = end_date = None
        is_current = False
        months = 0
        if period:
            start, end, is_current = period
            start_date = _format_month(*start)
            end_date = None if is_current else _format_month(*end)
            months = _month_index(*end) - _month_index(*start) + 1
            months = max(months, 1)
            intervals.append((_month_index(*start), _month_index(*end)))
        entries.append(
            ExperienceEntry(
                title=title,
                company=company,
                start_date=start_date,
                end_date=end_date,
                is_current=is_current,
                description=description,
                months=months,
            )
        )

    # Drop duplicates produced by multi-date lines.
    deduped: list[ExperienceEntry] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for entry in entries:
        key = (entry.title.lower(), (entry.company or "").lower(), entry.start_date)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    total_months = _total_months(intervals)
    return deduped, round(total_months / 12, 1)


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------


def _is_institution(line: str) -> bool:
    normalized = normalize(line)
    return any(hint in normalized for hint in _INSTITUTION_HINTS)


def _extract_year_text(line: str) -> str | None:
    years = [int(match.group(1)) for match in _YEAR_RE.finditer(line)]
    if not years:
        return None
    unique = list(dict.fromkeys(years))
    if len(unique) >= 2:
        return f"{unique[0]}-{unique[-1]}"
    return str(unique[0])


def _split_education_line(line: str) -> tuple[str, str | None]:
    parts = [part.strip(" -–—|,;") for part in re.split(r"\s*[—–|]\s*|\s+-\s+", line)]
    parts = [part for part in parts if part]
    if not parts:
        return line.strip(), None
    institution = next((part for part in parts if _is_institution(part)), None)
    degree_parts = [part for part in parts if part != institution and not _YEAR_RE.fullmatch(part)]
    degree = " ".join(degree_parts).strip() or parts[0]
    if institution == degree:
        institution = None
    return degree[:200], institution


def _parse_education(lines: list[str]) -> list[EducationEntry]:
    entries: list[EducationEntry] = []
    index = 0
    while index < len(lines):
        line = _clean_bullet(lines[index])
        if not line:
            index += 1
            continue
        level = detect_education_level(line)
        has_year = bool(_YEAR_RE.search(line))
        if level != EducationLevel.NONE or (has_year and _is_institution(line)):
            degree, institution = _split_education_line(line)
            year = _extract_year_text(line)
            if institution is None and index + 1 < len(lines) and _is_institution(lines[index + 1]):
                institution = _clean_bullet(lines[index + 1])[:200]
                index += 1
            if year is None and index + 1 < len(lines):
                next_line = _clean_bullet(lines[index + 1])
                if _YEAR_ONLY_RE.match(next_line):
                    year = _extract_year_text(next_line)
                    index += 1
            entries.append(
                EducationEntry(
                    degree=degree,
                    institution=institution,
                    year=year,
                    level=int(level),
                )
            )
        elif _is_institution(line) and entries and entries[-1].institution is None:
            entries[-1].institution = line[:200]
        index += 1

    if not entries:
        fallback = [_clean_bullet(line) for line in lines if _clean_bullet(line)][:3]
        entries = [
            EducationEntry(degree=line[:200], level=int(detect_education_level(line)))
            for line in fallback
        ]

    deduped: list[EducationEntry] = []
    seen: set[str] = set()
    for entry in entries:
        key = normalize(entry.degree)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


# ---------------------------------------------------------------------------
# Languages, certifications and projects
# ---------------------------------------------------------------------------

_LANGUAGE_NAMES: dict[str, str] = {
    "portugues": "Português",
    "ingles": "Inglês",
    "espanhol": "Espanhol",
    "frances": "Francês",
    "alemao": "Alemão",
    "italiano": "Italiano",
    "mandarim": "Mandarim",
    "japones": "Japonês",
    "coreano": "Coreano",
    "russo": "Russo",
    "arabe": "Árabe",
    "holandes": "Holandês",
    "english": "Inglês",
    "spanish": "Espanhol",
    "french": "Francês",
    "german": "Alemão",
    "portuguese": "Português",
    "mandarin": "Mandarim",
    "japanese": "Japonês",
    "korean": "Coreano",
    "russian": "Russo",
    "arabic": "Árabe",
}

_LEVEL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("nativo", "Nativo"),
    ("native", "Nativo"),
    ("fluente", "Fluente"),
    ("fluent", "Fluente"),
    ("avancado", "Avançado"),
    ("advanced", "Avançado"),
    ("intermediario", "Intermediário"),
    ("intermediate", "Intermediário"),
    ("basico", "Básico"),
    ("basic", "Básico"),
    ("iniciante", "Básico"),
    ("beginner", "Básico"),
)
_CEFR_PATTERN = re.compile(r"\b(c2|c1|b2|b1|a2|a1)\b")


def _detect_language_level(normalized_line: str) -> str | None:
    for keyword, label in _LEVEL_PATTERNS:
        if keyword in normalized_line:
            return label
    cefr = _CEFR_PATTERN.search(normalized_line)
    if cefr:
        code = cefr.group(1)
        if code in {"c2", "c1"}:
            return "Avançado"
        if code in {"b2", "b1"}:
            return "Intermediário"
        return "Básico"
    return None


def _parse_languages(lines: list[str]) -> list[LanguageEntry]:
    entries: list[LanguageEntry] = []
    seen: set[str] = set()
    for line in lines:
        clean = _clean_bullet(line)
        if not clean:
            continue
        normalized = normalize(clean)
        level = _detect_language_level(normalized)
        for alias, display in _LANGUAGE_NAMES.items():
            if re.search(rf"\b{re.escape(alias)}\b", normalized) and display not in seen:
                entries.append(LanguageEntry(name=display, level=level))
                seen.add(display)
    return entries


def _parse_list_section(lines: list[str], *, limit: int) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for line in lines:
        value = _clean_bullet(line)
        if len(value) < 3:
            continue
        key = normalize(value)
        if key in seen:
            continue
        seen.add(key)
        items.append(value[:300])
        if len(items) >= limit:
            break
    return items


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class ResumeParser:
    """Stateless parser: safe to reuse across requests."""

    def parse(self, text: str, *, now: datetime | None = None) -> ParsedResume:
        reference = now or datetime.now(UTC)
        cleaned = (text or "").strip()
        if not cleaned:
            return ParsedResume(metadata=ResumeMetadata())

        sections = split_sections(cleaned)
        header_lines = [line for line in sections.get("header", []) if line.strip()]

        experience, years_experience = _parse_experience(sections.get("experience", []), reference)
        education = _parse_education(sections.get("education", []))
        highest_level = max((entry.level for entry in education), default=0)
        sections_found = [
            name
            for name, lines in sections.items()
            if name != "header" and any(line.strip() for line in lines)
        ]

        return ParsedResume(
            contact=_parse_contact(cleaned, header_lines),
            summary=" ".join(
                _clean_bullet(line) for line in sections.get("summary", []) if line.strip()
            )[:1200],
            skills=find_skills(cleaned),
            education=education,
            experience=experience,
            languages=_parse_languages(sections.get("languages", [])),
            certifications=_parse_list_section(sections.get("certifications", []), limit=20),
            projects=_parse_list_section(sections.get("projects", []), limit=10),
            metadata=ResumeMetadata(
                word_count=count_words(cleaned),
                char_count=len(cleaned),
                language=detect_language(cleaned),
                sections_found=sections_found,
                years_experience=years_experience,
                education_level=highest_level,
            ),
        )


_DEFAULT_PARSER = ResumeParser()


def parse_resume(text: str, *, now: datetime | None = None) -> ParsedResume:
    """Convenience wrapper around :class:`ResumeParser`."""
    return _DEFAULT_PARSER.parse(text, now=now)
