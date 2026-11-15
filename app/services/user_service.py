"""User profile and account lifecycle operations."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, ValidationAppError
from app.core.security import (
    WeakPasswordError,
    hash_password,
    validate_password_strength,
    verify_password,
)
from app.db.base import utcnow
from app.db.models import Analysis, RefreshToken, Resume, User
from app.services.storage import Storage, StorageError

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    """Normalize e-mail addresses so uniqueness is case-insensitive."""
    return email.strip().lower()


async def update_profile(
    session: AsyncSession,
    user: User,
    *,
    full_name: str | None = None,
    email: str | None = None,
) -> User:
    if full_name is not None:
        cleaned = " ".join(full_name.split())
        if len(cleaned) < 2:
            raise ValidationAppError("Full name is too short", code="invalid_full_name")
        user.full_name = cleaned[:120]
    if email is not None:
        normalized = normalize_email(email)
        if normalized != user.email:
            existing = await session.scalar(select(User.id).where(User.email == normalized))
            if existing:
                raise ConflictError("Email already registered", code="email_already_registered")
            user.email = normalized
    await session.commit()
    await session.refresh(user)
    return user


async def change_password(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    current_password: str,
    new_password: str,
) -> None:
    valid = await asyncio.to_thread(verify_password, current_password, user.hashed_password)
    if not valid:
        raise ValidationAppError("Current password is incorrect", code="invalid_current_password")
    if current_password == new_password:
        raise ValidationAppError(
            "The new password must be different from the current one", code="password_unchanged"
        )
    try:
        validate_password_strength(new_password, min_length=settings.password_min_length)
    except WeakPasswordError as exc:
        raise ValidationAppError(
            "Password does not meet the security policy",
            code="weak_password",
            details={"problems": exc.problems},
        ) from exc

    hashed = await asyncio.to_thread(
        hash_password, new_password, iterations=settings.password_hash_iterations
    )
    user.hashed_password = hashed
    # Password rotation invalidates every existing session.
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()


async def delete_account(
    session: AsyncSession,
    storage: Storage,
    user: User,
    *,
    password: str,
) -> None:
    """Permanently delete the user, their resumes, analyses and stored files."""
    valid = await asyncio.to_thread(verify_password, password, user.hashed_password)
    if not valid:
        raise ValidationAppError("Password is incorrect", code="invalid_password")

    storage_keys = list(
        (await session.scalars(select(Resume.storage_key).where(Resume.user_id == user.id))).all()
    )
    await session.execute(delete(Analysis).where(Analysis.user_id == user.id))
    await session.execute(delete(Resume).where(Resume.user_id == user.id))
    await session.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await session.delete(user)
    await session.commit()

    for key in storage_keys:
        try:
            storage.delete(key)
        except StorageError:  # pragma: no cover - defensive cleanup
            logger.warning("Could not delete stored file %s during account deletion", key)
