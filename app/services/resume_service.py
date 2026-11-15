"""Resume upload, retrieval and deletion use cases."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.extractors import (
    CorruptedDocumentError,
    EmptyDocumentError,
    UnsupportedFormatError,
    extract_text,
    file_extension,
    sanitize_filename,
)
from app.analyzer.parser import ResumeParser
from app.core.config import Settings
from app.core.exceptions import (
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    ValidationAppError,
)
from app.core.pagination import PageParams
from app.db.models import Analysis, Resume, User
from app.services.storage import Storage, StorageError

logger = logging.getLogger(__name__)
_parser = ResumeParser()


async def create_resume(
    session: AsyncSession,
    settings: Settings,
    storage: Storage,
    user: User,
    *,
    filename: str,
    content_type: str | None,
    data: bytes,
    title: str | None = None,
) -> Resume:
    """Validate, extract, parse and persist an uploaded resume."""
    safe_name = sanitize_filename(filename)
    extension = file_extension(safe_name)
    if extension not in settings.allowed_extensions:
        allowed = ", ".join(sorted(settings.allowed_extensions))
        raise UnsupportedMediaTypeError(
            f"Unsupported file type '{extension or 'unknown'}'. Allowed types: {allowed}",
            code="unsupported_file_type",
        )
    if not data:
        raise ValidationAppError("The uploaded file is empty", code="empty_file")
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            f"The uploaded file exceeds the {settings.max_upload_bytes} byte limit",
            code="file_too_large",
            details={"max_upload_bytes": settings.max_upload_bytes},
        )

    try:
        text = await asyncio.to_thread(extract_text, data, safe_name)
    except UnsupportedFormatError as exc:
        raise UnsupportedMediaTypeError(str(exc), code="unsupported_file_type") from exc
    except EmptyDocumentError as exc:
        raise ValidationAppError(str(exc), code="empty_document") from exc
    except CorruptedDocumentError as exc:
        raise ValidationAppError(str(exc), code="invalid_document") from exc

    if len(text) > settings.max_resume_chars:
        text = text[: settings.max_resume_chars]

    parsed = await asyncio.to_thread(_parser.parse, text)
    stored = storage.save(data, user_id=user.id, extension=extension)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    resume_title = (title or Path(safe_name).stem or "Currículo").strip()[:200]
    resume = Resume(
        user_id=user.id,
        title=resume_title,
        original_filename=safe_name,
        content_type=(content_type or "application/octet-stream")[:125],
        size_bytes=len(data),
        storage_key=stored.key,
        text=text,
        text_sha256=digest,
        language=parsed.metadata.language,
        word_count=parsed.metadata.word_count,
        years_experience=parsed.metadata.years_experience,
        education_level=parsed.metadata.education_level,
        skills=parsed.skills,
        parsed=parsed.to_dict(),
    )
    session.add(resume)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        try:
            storage.delete(stored.key)
        except StorageError:  # pragma: no cover - defensive cleanup
            logger.warning("Could not remove orphaned upload %s", stored.key)
        raise
    await session.refresh(resume)
    return resume


async def list_resumes(
    session: AsyncSession,
    user_id: str,
    params: PageParams,
    *,
    search: str | None = None,
) -> tuple[list[Resume], int]:
    conditions = [Resume.user_id == user_id]
    if search:
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if escaped:
            conditions.append(Resume.title.ilike(f"%{escaped}%", escape="\\"))

    total = await session.scalar(select(func.count(Resume.id)).where(*conditions)) or 0
    rows = (
        await session.scalars(
            select(Resume)
            .where(*conditions)
            .order_by(Resume.created_at.desc(), Resume.id.desc())
            .offset(params.offset)
            .limit(params.page_size)
        )
    ).all()
    return list(rows), int(total)


async def get_resume(session: AsyncSession, user_id: str, resume_id: str) -> Resume:
    resume = await session.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    )
    if resume is None:
        raise NotFoundError("Resume not found", code="resume_not_found")
    return resume


async def delete_resume(
    session: AsyncSession,
    storage: Storage,
    user_id: str,
    resume_id: str,
) -> None:
    resume = await get_resume(session, user_id, resume_id)
    storage_key = resume.storage_key
    await session.execute(delete(Analysis).where(Analysis.resume_id == resume.id))
    await session.delete(resume)
    await session.commit()
    try:
        storage.delete(storage_key)
    except StorageError:  # pragma: no cover - defensive cleanup
        logger.warning("Could not delete stored file %s", storage_key)
