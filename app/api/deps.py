"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer.pipeline import ResumeAnalysisPipeline
from app.core.config import Settings
from app.core.exceptions import ForbiddenError, RateLimitError, UnauthorizedError
from app.core.security import TokenError, decode_access_token
from app.db.models import User
from app.services.storage import Storage

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
    description="JWT de acesso obtido em `POST /api/v1/auth/login` (username = e-mail).",
)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> Storage:
    return request.app.state.storage


def get_pipeline(request: Request) -> ResumeAnalysisPipeline:
    return request.app.state.pipeline


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session and roll back on unhandled errors."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if not token:
        raise UnauthorizedError("Not authenticated", code="not_authenticated")
    try:
        payload = decode_access_token(token, settings)
    except TokenError as exc:
        raise UnauthorizedError("Invalid or expired access token", code="invalid_token") from exc

    user = await session.get(User, payload["sub"])
    if user is None:
        raise UnauthorizedError("User no longer exists", code="invalid_token")
    if not user.is_active:
        raise ForbiddenError("Account is disabled", code="account_disabled")
    return user


async def get_optional_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User | None:
    if not token:
        return None
    try:
        payload = decode_access_token(token, settings)
    except TokenError:
        return None
    user = await session.get(User, payload["sub"])
    if user is None or not user.is_active:
        return None
    return user


async def enforce_auth_rate_limit(request: Request) -> None:
    """Protect authentication endpoints against credential stuffing."""
    settings: Settings = request.app.state.settings
    limiter = request.app.state.auth_rate_limiter
    if not settings.rate_limit_enabled or limiter is None:
        return
    client_host = request.client.host if request.client else "unknown"
    allowed, retry_after = await limiter.check(f"auth:{client_host}")
    if not allowed:
        raise RateLimitError(retry_after=retry_after)
