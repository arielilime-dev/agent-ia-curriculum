"""Analysis creation, listing and retrieval endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.pipeline import ResumeAnalysisPipeline
from app.api.deps import get_current_user, get_pipeline, get_session
from app.core.pagination import Page, PageParams
from app.db.models import Analysis, User
from app.schemas.analysis import AnalysisCreate, AnalysisRead, AnalysisSummary
from app.services.analysis_service import (
    create_analysis,
    delete_analysis,
    get_analysis,
    list_analyses,
)

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post(
    "",
    response_model=AnalysisRead,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze a resume (optionally against a job description)",
)
async def create(
    payload: AnalysisCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    pipeline: ResumeAnalysisPipeline = Depends(get_pipeline),
) -> Analysis:
    return await create_analysis(
        session,
        pipeline,
        user,
        resume_id=payload.resume_id,
        job_description=payload.job_description,
        job_title=payload.job_title,
    )


@router.get("", response_model=Page[AnalysisSummary], summary="List analyses")
async def list_my_analyses(
    params: PageParams = Depends(),
    resume_id: str | None = Query(default=None, max_length=36),
    min_score: float | None = Query(default=None, ge=0, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[AnalysisSummary]:
    items, total = await list_analyses(
        session, user.id, params, resume_id=resume_id, min_score=min_score
    )
    return Page.build([AnalysisSummary.model_validate(item) for item in items], total, params)


@router.get("/{analysis_id}", response_model=AnalysisRead, summary="Get an analysis")
async def get_one(
    analysis_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Analysis:
    return await get_analysis(session, user.id, analysis_id)


@router.delete(
    "/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an analysis"
)
async def delete_one(
    analysis_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await delete_analysis(session, user.id, analysis_id)
