"""Safe text extraction from PDF, DOCX and plain-text resumes."""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".md"})
MAX_PDF_PAGES = 50

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LINE_SPACES_RE = re.compile(r"[ \t]+")


class ExtractionError(Exception):
    """Base class for document extraction failures."""


class UnsupportedFormatError(ExtractionError):
    """The file extension is not supported."""


class EmptyDocumentError(ExtractionError):
    """The document contains no extractable text."""


class CorruptedDocumentError(ExtractionError):
    """The document is encrypted, truncated or otherwise unreadable."""


def file_extension(filename: str) -> str:
    """Return the lowercase extension of *filename*."""
    return Path(filename or "").suffix.lower()


def _clean_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS_RE.sub("", text)
    lines = [_LINE_SPACES_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _decode_text(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    # latin-1 maps every byte, so this never fails.
    return data.decode("latin-1", errors="replace")


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ExtractionError("PDF support requires the 'pypdf' package") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise CorruptedDocumentError("Encrypted PDF documents are not supported")
    except CorruptedDocumentError:
        raise
    except Exception as exc:
        raise CorruptedDocumentError("Could not read the PDF document") from exc

    chunks: list[str] = []
    try:
        for page in reader.pages[:MAX_PDF_PAGES]:
            chunks.append(page.extract_text() or "")
    except Exception as exc:
        raise CorruptedDocumentError("Could not extract text from the PDF document") from exc
    return "\n\n".join(chunks)


def _extract_docx(data: bytes) -> str:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ExtractionError("DOCX support requires the 'python-docx' package") from exc

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise CorruptedDocumentError("Could not read the DOCX document") from exc

    parts: list[str] = []
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            parts.append(paragraph.text)
    for table in document.tables:
        for row in table.rows:
            cells: list[str] = []
            for cell in row.cells:
                value = cell.text.strip()
                # Merged cells are reported multiple times by python-docx.
                if value and (not cells or cells[-1] != value):
                    cells.append(value)
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def extract_text(data: bytes, filename: str) -> str:
    """Extract clean plain text from an uploaded resume.

    Raises:
        UnsupportedFormatError: for extensions outside :data:`SUPPORTED_EXTENSIONS`.
        EmptyDocumentError: when there is no file content or no extractable text.
        CorruptedDocumentError: when a PDF/DOCX cannot be parsed.
    """
    if not data:
        raise EmptyDocumentError("The uploaded file is empty")
    extension = file_extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFormatError(
            f"Unsupported file type '{extension or 'unknown'}'. Supported types: {supported}"
        )

    if extension in {".txt", ".md"}:
        raw = _decode_text(data)
    elif extension == ".pdf":
        raw = _extract_pdf(data)
    else:
        raw = _extract_docx(data)

    text = _clean_text(raw)
    if not text:
        raise EmptyDocumentError("No extractable text was found in the document")
    return text


def sanitize_filename(filename: str) -> str:
    """Strip directories and control characters from a client-provided name."""
    name = Path(filename or "").name
    name = unicodedata.normalize("NFKC", name)
    name = _CONTROL_CHARS_RE.sub("", name).strip().strip(".")
    return name[:255] or "resume"
