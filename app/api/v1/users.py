"""Current-user profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session, get_settings, get_storage
from app.core.config import Settings
from app.db.models import User
from app.schemas.analysis import DashboardStats
from app.schemas.user import AccountDeleteRequest, PasswordChange, UserRead, UserUpdate
from app.services.analysis_service import dashboard_stats
from app.services.storage import Storage
from app.services.user_service import change_password, delete_account, update_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead, summary="Get the authenticated user")
async def read_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserRead, summary="Update profile data")
async def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    return await update_profile(
        session,
        user,
        full_name=payload.full_name,
        email=str(payload.email) if payload.email else None,
    )


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the password (revokes all sessions)",
)
async def change_my_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> None:
    await change_password(
        session,
        settings,
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )


@router.get("/me/stats", response_model=DashboardStats, summary="Dashboard aggregates")
async def my_stats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await dashboard_stats(session, user.id)


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the account and every stored document",
)
async def delete_me(
    payload: AccountDeleteRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> None:
    await delete_account(session, storage, user, password=payload.password)
