"""Authentication use cases: registration, login, tokens and revocation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError, ValidationAppError
from app.core.security import (
    WeakPasswordError,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    validate_password_strength,
    verify_password,
)
from app.db.base import utcnow
from app.db.models import RefreshToken, User
from app.services.user_service import normalize_email


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int


@lru_cache(maxsize=8)
def _dummy_hash(iterations: int) -> str:
    """A fixed hash used to keep login timing constant for unknown e-mails."""
    return hash_password(
        "timing-attack-mitigation-password",
        iterations=iterations,
        salt=b"0123456789abcdef",
    )


async def register_user(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    full_name: str,
    password: str,
) -> User:
    """Create a new account with a hashed password."""
    normalized_email = normalize_email(email)
    try:
        validate_password_strength(password, min_length=settings.password_min_length)
    except WeakPasswordError as exc:
        raise ValidationAppError(
            "Password does not meet the security policy",
            code="weak_password",
            details={"problems": exc.problems},
        ) from exc

    existing = await session.scalar(select(User.id).where(User.email == normalized_email))
    if existing:
        raise ConflictError("Email already registered", code="email_already_registered")

    hashed = await asyncio.to_thread(
        hash_password, password, iterations=settings.password_hash_iterations
    )
    user = User(
        email=normalized_email,
        full_name=full_name.strip(),
        hashed_password=hashed,
        is_active=True,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("Email already registered", code="email_already_registered") from exc
    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    password: str,
) -> User:
    """Validate credentials and update ``last_login_at``."""
    normalized_email = normalize_email(email)
    user = await session.scalar(select(User).where(User.email == normalized_email))
    stored_hash = user.hashed_password if user else _dummy_hash(settings.password_hash_iterations)
    valid = await asyncio.to_thread(verify_password, password, stored_hash)
    if user is None or not valid:
        raise UnauthorizedError("Invalid email or password", code="invalid_credentials")
    if not user.is_active:
        raise ForbiddenError("Account is disabled", code="account_disabled")

    user.last_login_at = utcnow()
    await session.commit()
    await session.refresh(user)
    return user


async def issue_tokens(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> IssuedTokens:
    """Create a JWT access token and a rotating refresh token."""
    access_token = create_access_token(user.id, settings)
    raw_refresh = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:300] or None,
            ip_address=(ip_address or "")[:45] or None,
        )
    )
    await session.commit()
    return IssuedTokens(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def rotate_refresh_token(
    session: AsyncSession,
    settings: Settings,
    *,
    refresh_token: str,
) -> tuple[User, IssuedTokens]:
    """Exchange a refresh token for a new pair, rotating (revoking) the old one.

    Reusing an already-rotated token is treated as theft: every session of that
    user is revoked and the request fails.
    """
    token_hash = hash_refresh_token(refresh_token)
    stored = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if stored is None:
        raise UnauthorizedError("Invalid refresh token", code="invalid_refresh_token")

    now = utcnow()
    if stored.revoked_at is not None:
        await revoke_all_user_tokens(session, stored.user_id)
        raise UnauthorizedError("Refresh token already used", code="refresh_token_reused")
    if stored.expires_at <= now:
        raise UnauthorizedError("Refresh token expired", code="refresh_token_expired")

    user = await session.get(User, stored.user_id)
    if user is None:
        raise UnauthorizedError("Invalid refresh token", code="invalid_refresh_token")
    if not user.is_active:
        raise ForbiddenError("Account is disabled", code="account_disabled")

    stored.revoked_at = now
    raw_refresh = generate_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=now + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=stored.user_agent,
            ip_address=stored.ip_address,
        )
    )
    await session.commit()
    return user, IssuedTokens(
        access_token=create_access_token(user.id, settings),
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


async def revoke_all_user_tokens(session: AsyncSession, user_id: str) -> None:
    """Revoke every active refresh token of a user (idempotent)."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()


async def logout(
    session: AsyncSession,
    user: User,
    *,
    refresh_token: str | None = None,
) -> None:
    """Revoke one refresh token, or all of the user's sessions when omitted."""
    if refresh_token:
        stored = await session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(refresh_token),
                RefreshToken.user_id == user.id,
            )
        )
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = utcnow()
        await session.commit()
        return
    await revoke_all_user_tokens(session, user.id)
