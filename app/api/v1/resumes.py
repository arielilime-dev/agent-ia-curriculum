"""Resume upload, listing, detail and deletion endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings, get_storage
from app.core.config import Settings
from app.core.exceptions import PayloadTooLargeError
from app.core.pagination import Page, PageParams
from app.db.models import Resume, User
from app.schemas.resume import ResumeRead, ResumeSummary, ResumeText
from app.services.resume_service import create_resume, delete_resume, get_resume, list_resumes
from app.services.storage import Storage

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post(
    "",
    response_model=ResumeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and analyze a resume (PDF, DOCX, TXT or MD)",
)
async def upload_resume(
    file: UploadFile = File(..., description="Resume file"),
    title: str | None = Form(default=None, max_length=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    storage: Storage = Depends(get_storage),
) -> Resume:
    # Read at most one byte over the limit to detect oversized uploads early.
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            f"The uploaded file exceeds the {settings.max_upload_bytes} byte limit",
            code="file_too_large",
        )
    return await create_resume(
        session,
        settings,
        storage,
        user,
        filename=file.filename or "resume",
        content_type=file.content_type,
        data=data,
        title=title,
    )


@router.get("", response_model=Page[ResumeSummary], summary="List resumes")
async def list_my_resumes(
    params: PageParams = Depends(),
    search: str | None = Query(default=None, max_length=100, description="Filter by title"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[ResumeSummary]:
    items, total = await list_resumes(session, user.id, params, search=search)
    return Page.build([ResumeSummary.model_validate(item) for item in items], total, params)


@router.get("/{resume_id}", response_model=ResumeRead, summary="Get a resume with parsed data")
async def get_my_resume(
    resume_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Resume:
    return await get_resume(session, user.id, resume_id)


@router.get("/{resume_id}/text", response_model=ResumeText, summary="Get the extracted text")
async def get_my_resume_text(
    resume_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ResumeText:
    resume = await get_resume(session, user.id, resume_id)
    return ResumeText(id=resume.id, text=resume.text, word_count=resume.word_count)


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a resume")
async def delete_my_resume(
    resume_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> None:
    await delete_resume(session, storage, user.id, resume_id)
