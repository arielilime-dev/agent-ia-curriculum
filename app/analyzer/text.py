"""Text normalization and lightweight NLP helpers.

Everything here is deterministic and dependency-free (standard library only),
which keeps the analyzer testable and cheap to run offline.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_ACCENT_TABLE = str.maketrans(
    "áàâãäåéèêëíìîïóòôõöúùûüçñýÿÁÀÂÃÄÅÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑÝŸ",
    "aaaaaaeeeeiiiiooooouuuucnyyaaaaaaeeeeiiiiooooouuuucnyy",
)

_WHITESPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^a-z0-9+#.\-\s]")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9+#._'\-]*")


def strip_accents(value: str) -> str:
    """Remove diacritics (``João`` -> ``Joao``)."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize(value: str) -> str:
    """Lowercase, accent-fold and collapse punctuation/whitespace.

    ``+``, ``#`` and ``.`` are preserved because they are meaningful in tech
    terms such as ``C++``, ``C#`` and ``Node.js``.
    """
    if not value:
        return ""
    text = strip_accents(str(value)).lower().translate(_ACCENT_TABLE)
    text = _NON_WORD_RE.sub(" ", text)
    text = text.replace("-", " ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def tokenize(value: str) -> list[str]:
    """Split *value* into normalized word tokens."""
    return normalize(value).split()


def count_words(value: str) -> int:
    """Count word-like tokens (useful as a resume-length signal)."""
    return len(_WORD_RE.findall(value or ""))


def split_sentences(value: str) -> list[str]:
    """Naive sentence splitter that keeps decimal numbers intact."""
    if not value:
        return []
    parts = re.split(r"(?<=[.!?])\s+", value.replace("\n", " "))
    return [part.strip() for part in parts if part.strip()]


# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------

STOPWORDS_PT: frozenset[str] = frozenset(
    [
        "a",
        "ao",
        "aos",
        "aquela",
        "aquelas",
        "aquele",
        "aqueles",
        "aquilo",
        "as",
        "ate",
        "aos",
        "com",
        "como",
        "da",
        "das",
        "de",
        "dela",
        "delas",
        "dele",
        "deles",
        "depois",
        "do",
        "dos",
        "e",
        "ela",
        "elas",
        "ele",
        "eles",
        "em",
        "entre",
        "era",
        "eram",
        "essa",
        "essas",
        "esse",
        "esses",
        "esta",
        "estado",
        "estas",
        "este",
        "estes",
        "eu",
        "foi",
        "foram",
        "ha",
        "isso",
        "isto",
        "ja",
        "lhe",
        "lhes",
        "mais",
        "mas",
        "me",
        "mesmo",
        "meu",
        "meus",
        "minha",
        "minhas",
        "muito",
        "na",
        "nao",
        "nas",
        "nem",
        "no",
        "nos",
        "nossa",
        "nossas",
        "nosso",
        "nossos",
        "num",
        "numa",
        "o",
        "os",
        "ou",
        "para",
        "pela",
        "pelas",
        "pelo",
        "pelos",
        "por",
        "qual",
        "quando",
        "que",
        "quem",
        "sao",
        "se",
        "sem",
        "ser",
        "seu",
        "seus",
        "so",
        "sobre",
        "sua",
        "suas",
        "tambem",
        "te",
        "tem",
        "tempo",
        "tenho",
        "ter",
        "teu",
        "teus",
        "tu",
        "tua",
        "tuas",
        "um",
        "uma",
        "umas",
        "uns",
        "voce",
        "voces",
        "durante",
        "desde",
        "ate",
        "onde",
        "assim",
        "cada",
        "todo",
        "toda",
        "todos",
        "todas",
        "outro",
        "outra",
        "experiencia",
        "profissional",
        "curriculo",
        "resume",
        "vaga",
        "oportunidades",
        "oportunidade",
        "empresa",
        "empresas",
        "cargo",
        "area",
        "trabalho",
        "atuacao",
        "atividades",
        "responsabilidades",
        "requisitos",
        "diferenciais",
        "desejavel",
        "obrigatorio",
        "necessario",
        "necessario",
    ]
)

STOPWORDS_EN: frozenset[str] = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "experience",
        "professional",
        "resume",
        "job",
        "opportunity",
        "company",
        "responsibilities",
        "requirements",
        "qualifications",
        "preferred",
        "required",
    ]
)

STOPWORDS: frozenset[str] = STOPWORDS_PT | STOPWORDS_EN

# Recruitment boilerplate that should never become a scoring keyword.
JOB_BOILERPLATE: frozenset[str] = frozenset(
    [
        "vaga",
        "vagas",
        "oportunidades",
        "candidato",
        "candidatos",
        "candidate",
        "candidates",
        "requisitos",
        "responsabilidades",
        "atividades",
        "atribuicoes",
        "beneficios",
        "salario",
        "remuneracao",
        "contratacao",
        "empresa",
        "empresas",
        "time",
        "equipe",
        "trabalho",
        "trabalhar",
        "atuacao",
        "atuar",
        "desenvolvimento",
        "desenvolvimento",
        "desenvolver",
        "conhecimento",
        "conhecimentos",
        "experiencia",
        "profissional",
        "diferenciais",
        "desejavel",
        "necessario",
        "obrigatorio",
        "hibrido",
        "presencial",
        "remoto",
        "meio",
        "periodo",
        "full",
        "time",
        "tempo",
        "integral",
        "jornada",
        "carga",
        "horaria",
        "CLT",
        "PJ",
    ]
)

ACTION_VERBS: frozenset[str] = frozenset(
    [
        "desenvolvi",
        "desenvolveu",
        "desenvolvi",
        "implementei",
        "implementou",
        "implementado",
        "criei",
        "criou",
        "liderei",
        "liderou",
        "gerenciei",
        "gerenciou",
        "coordenei",
        "coordenou",
        "arquitetei",
        "arquitetou",
        "otimizei",
        "otimizou",
        "reduzi",
        "reduziu",
        "aumentei",
        "aumentou",
        "entreguei",
        "entregou",
        "automatizei",
        "automatizou",
        "migrei",
        "migrou",
        "projetei",
        "projetou",
        "construi",
        "construiu",
        "integrei",
        "integrou",
        "negociei",
        "negociaou",
        "mentorei",
        "mentoria",
        "treinei",
        "treinou",
        "analisei",
        "analisou",
        "developed",
        "implemented",
        "built",
        "designed",
        "led",
        "managed",
        "coordinated",
        "architected",
        "optimized",
        "reduced",
        "increased",
        "delivered",
        "automated",
        "migrated",
        "integrated",
        "negotiated",
        "mentored",
        "trained",
        "analyzed",
        "created",
        "launched",
        "scaled",
        "improved",
    ]
)


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------


def extract_keywords(
    text: str,
    *,
    limit: int = 25,
    min_length: int = 3,
    exclude: Iterable[str] = (),
) -> list[str]:
    """Return salient tokens ranked by frequency, then first appearance."""
    if not text:
        return []
    tokens = tokenize(text)
    excluded = STOPWORDS | frozenset(exclude)
    filtered: list[str] = []
    first_seen: dict[str, int] = {}
    for index, token in enumerate(tokens):
        if len(token) < min_length or token.isdigit():
            continue
        if token in excluded:
            continue
        filtered.append(token)
        first_seen.setdefault(token, index)
    if not filtered:
        return []
    counter = Counter(filtered)
    ranked = sorted(counter, key=lambda token: (-counter[token], first_seen[token]))
    return ranked[:limit]


def keyword_present(keyword: str, resume_tokens: set[str], normalized_text: str) -> bool:
    """Check keyword presence as token or compact phrase."""
    if keyword in resume_tokens:
        return True
    compact = keyword.replace(" ", "")
    return bool(" " in keyword and compact and compact in normalized_text.replace(" ", ""))


def count_action_verbs(text: str) -> int:
    """Number of distinct achievement-oriented verbs found in *text*."""
    tokens = set(tokenize(text))
    return len(tokens & ACTION_VERBS)


def count_quantified_achievements(text: str) -> int:
    """Count percentages and large numbers that suggest measurable impact."""
    if not text:
        return 0
    percentages = len(re.findall(r"\d+(?:[.,]\d+)?\s?%", text))
    large_numbers = len(re.findall(r"(?<![\d.])\d{2,}(?![\d.])", text))
    currency = len(re.findall(r"(?:R\$|US\$|\$)\s?\d", text))
    return percentages + large_numbers + currency


# ---------------------------------------------------------------------------
# Contact extraction
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+)(?![\w-])"
)
_PHONE_CHUNK_RE = re.compile(
    r"(?<![\w/])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,4}\)[\s.-]?)?\d[\d\s().-]{6,18}\d(?![\w/])"
)
_YEAR_RANGE_RE = re.compile(r"(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}")
_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"'()\[\]]+"
    r"|(?<![\w@.])(?:linkedin\.com|github\.com|gitlab\.com|behance\.net)/[^\s<>\"'()\[\]]*"
    r"|(?<![\w@.])(?:[a-z0-9-]+\.)+(?:dev|io|me|com\.br|com|net|org)(?:/[^\s<>\"'()\[\]]*)?",
    re.IGNORECASE,
)


def extract_emails(text: str) -> list[str]:
    """Return unique lowercase e-mail addresses in order of appearance."""
    seen: list[str] = []
    for match in _EMAIL_RE.finditer(text or ""):
        email = match.group(1).strip(".").lower()
        if email not in seen:
            seen.append(email)
    return seen


def _format_phone(raw: str) -> str:
    return _WHITESPACE_RE.sub(" ", raw).strip(" .-")


def extract_phones(text: str) -> list[str]:
    """Extract plausible phone numbers, rejecting year ranges and IDs."""
    phones: list[str] = []
    for match in _PHONE_CHUNK_RE.finditer(text or ""):
        raw = match.group().strip()
        if _YEAR_RANGE_RE.search(raw):
            continue
        digits = re.sub(r"\D", "", raw)
        if not 8 <= len(digits) <= 15:
            continue
        if raw.count(".") + raw.count("-") > 3:
            continue
        formatted = _format_phone(raw)
        if formatted and formatted not in phones:
            phones.append(formatted)
    return phones


def extract_urls(text: str) -> dict[str, str]:
    """Classify profile links into ``linkedin``, ``github``, ``gitlab`` or ``website``."""
    links: dict[str, str] = {}
    for match in _URL_RE.finditer(text or ""):
        url = match.group().rstrip(".,;:)]}\"'")
        lowered = url.lower()
        if "linkedin.com" in lowered:
            links.setdefault("linkedin", url)
        elif "github.com" in lowered:
            links.setdefault("github", url)
        elif "gitlab.com" in lowered:
            links.setdefault("gitlab", url)
        else:
            links.setdefault("website", url)
    return links


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_PT_MARKERS = frozenset(
    [
        "de",
        "da",
        "do",
        "para",
        "com",
        "uma",
        "um",
        "os",
        "as",
        "em",
        "no",
        "na",
        "por",
        "que",
        "meu",
        "minha",
        "sou",
        "formado",
        "formada",
        "experiencia",
        "profissional",
        "curriculo",
        "brasileiro",
        "brasileira",
    ]
)
_EN_MARKERS = frozenset(
    [
        "the",
        "and",
        "with",
        "for",
        "of",
        "to",
        "in",
        "my",
        "is",
        "was",
        "are",
        "experience",
        "professional",
        "resume",
        "bachelor",
        "university",
        "worked",
        "developed",
    ]
)


def detect_language(text: str) -> str:
    """Very small heuristic returning ``pt``, ``en`` or ``unknown``."""
    tokens = tokenize(text)
    if not tokens:
        return "unknown"
    pt_hits = sum(1 for token in tokens if token in _PT_MARKERS)
    en_hits = sum(1 for token in tokens if token in _EN_MARKERS)
    if pt_hits == 0 and en_hits == 0:
        return "unknown"
    return "pt" if pt_hits >= en_hits else "en"
