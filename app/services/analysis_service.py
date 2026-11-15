"""Analysis use cases and dashboard aggregation."""

from __future__ import annotations

from collections import Counter
from time import perf_counter

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.pipeline import ResumeAnalysisPipeline
from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.pagination import PageParams
from app.db.models import Analysis, Resume, User

MAX_JOB_DESCRIPTION_CHARS = 20_000


async def create_analysis(
    session: AsyncSession,
    pipeline: ResumeAnalysisPipeline,
    user: User,
    *,
    resume_id: str,
    job_description: str | None = None,
    job_title: str | None = None,
) -> Analysis:
    resume = await session.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    if resume is None:
        raise NotFoundError("Resume not found", code="resume_not_found")

    description = (job_description or "").strip() or None
    if description and len(description) > MAX_JOB_DESCRIPTION_CHARS:
        raise ValidationAppError(
            f"Job description exceeds {MAX_JOB_DESCRIPTION_CHARS} characters",
            code="job_description_too_long",
        )
    title = (job_title or "").strip()[:200] or None

    started = perf_counter()
    outcome = await pipeline.analyze(
        resume.text,
        job_description=description,
        job_title=title,
    )
    duration_ms = max(int((perf_counter() - started) * 1000), 0)
    result = outcome.result

    analysis = Analysis(
        user_id=user.id,
        resume_id=resume.id,
        job_title=title,
        job_description=description,
        overall_score=result["overall_score"],
        verdict=result["verdict"],
        breakdown=result["breakdown"],
        matched_skills=result["matched_skills"],
        missing_skills=result["missing_skills"],
        matched_keywords=result["matched_keywords"],
        missing_keywords=result["missing_keywords"],
        strengths=result["strengths"],
        suggestions=result["suggestions"],
        ats_checks=result["ats_checks"],
        summary=result["summary"],
        ai_provider=outcome.ai_provider,
        ai_model=outcome.ai_model,
        ai_degraded=outcome.ai_degraded,
        duration_ms=duration_ms,
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)
    return analysis


async def list_analyses(
    session: AsyncSession,
    user_id: str,
    params: PageParams,
    *,
    resume_id: str | None = None,
    min_score: float | None = None,
) -> tuple[list[Analysis], int]:
    conditions = [Analysis.user_id == user_id]
    if resume_id:
        conditions.append(Analysis.resume_id == resume_id)
    if min_score is not None:
        conditions.append(Analysis.overall_score >= min_score)

    total = await session.scalar(select(func.count(Analysis.id)).where(*conditions)) or 0
    rows = (
        await session.scalars(
            select(Analysis)
            .where(*conditions)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .offset(params.offset)
            .limit(params.page_size)
        )
    ).all()
    return list(rows), int(total)


async def get_analysis(session: AsyncSession, user_id: str, analysis_id: str) -> Analysis:
    analysis = await session.scalar(
        select(Analysis).where(Analysis.id == analysis_id, Analysis.user_id == user_id)
    )
    if analysis is None:
        raise NotFoundError("Analysis not found", code="analysis_not_found")
    return analysis


async def delete_analysis(session: AsyncSession, user_id: str, analysis_id: str) -> None:
    analysis = await get_analysis(session, user_id, analysis_id)
    await session.execute(delete(Analysis).where(Analysis.id == analysis.id))
    await session.commit()


async def dashboard_stats(session: AsyncSession, user_id: str) -> dict:
    """Aggregated numbers for the user dashboard."""
    total_resumes = (
        await session.scalar(select(func.count(Resume.id)).where(Resume.user_id == user_id)) or 0
    )
    total_analyses = (
        await session.scalar(select(func.count(Analysis.id)).where(Analysis.user_id == user_id))
        or 0
    )
    average_score, best_score = (
        await session.execute(
            select(func.avg(Analysis.overall_score), func.max(Analysis.overall_score)).where(
                Analysis.user_id == user_id
            )
        )
    ).one()

    skill_counter: Counter[str] = Counter()
    for skills in (
        await session.scalars(select(Resume.skills).where(Resume.user_id == user_id))
    ).all():
        for skill in skills or []:
            skill_counter[skill] += 1

    recent = (
        await session.scalars(
            select(Analysis)
            .where(Analysis.user_id == user_id)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(5)
        )
    ).all()

    return {
        "total_resumes": int(total_resumes),
        "total_analyses": int(total_analyses),
        "average_score": round(float(average_score), 1) if average_score is not None else None,
        "best_score": round(float(best_score), 1) if best_score is not None else None,
        "top_skills": [
            {"skill": skill, "count": count} for skill, count in skill_counter.most_common(8)
        ],
        "recent_analyses": list(recent),
    }
