"""Authentication endpoints: register, login, refresh and logout."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    enforce_auth_rate_limit,
    get_current_user,
    get_session,
    get_settings,
)
from app.core.config import Settings
from app.db.models import User
from app.schemas.auth import (
    AuthResponse,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserRead
from app.services.auth_service import (
    authenticate_user,
    issue_tokens,
    logout,
    register_user,
    rotate_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _request_context(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    client_host = request.client.host if request.client else None
    return user_agent, client_host


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    user = await register_user(
        session,
        settings,
        email=str(payload.email),
        full_name=payload.full_name,
        password=payload.password,
    )
    user_agent, client_host = _request_context(request)
    tokens = await issue_tokens(
        session, settings, user, user_agent=user_agent, ip_address=client_host
    )
    return AuthResponse(
        user=UserRead.model_validate(user),
        tokens=TokenResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
        ),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Exchange credentials for a token pair",
    description=(
        "OAuth2 password flow. Use your **e-mail** in the `username` field. "
        "The returned `refresh_token` can be rotated at `POST /auth/refresh`."
    ),
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    user = await authenticate_user(
        session,
        settings,
        email=form_data.username,
        password=form_data.password,
    )
    user_agent, client_host = _request_context(request)
    tokens = await issue_tokens(
        session, settings, user, user_agent=user_agent, ip_address=client_host
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate a refresh token",
    dependencies=[Depends(enforce_auth_rate_limit)],
)
async def refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    _user, tokens = await rotate_refresh_token(
        session, settings, refresh_token=payload.refresh_token
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke refresh tokens")
async def logout_endpoint(
    payload: LogoutRequest | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await logout(session, user, refresh_token=payload.refresh_token if payload else None)
