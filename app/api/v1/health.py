"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, get_settings
from app.core.config import Settings
from app.core.exceptions import AppError
from app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/health/live", response_model=HealthResponse, summary="Kubernetes liveness probe")
async def live(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="alive", version=settings.app_version, environment=settings.environment
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready(session: AsyncSession = Depends(get_session)) -> ReadinessResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - readiness must never leak internals
        raise AppError(
            "Database is not available",
            status_code=503,
            code="database_unavailable",
        ) from exc
    return ReadinessResponse(status="ready", database="ok")
