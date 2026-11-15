"""Authentication request/response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    # The full password policy (length, complexity, blocklist) lives in the
    # service layer so that clients receive a detailed `weak_password` error.
    password: str = Field(min_length=1, max_length=128)

    @field_validator("full_name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("full_name must contain at least 2 characters")
        return cleaned


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class AuthResponse(BaseModel):
    user: UserRead
    tokens: TokenResponse


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class LogoutRequest(BaseModel):
    """When ``refresh_token`` is omitted every session of the user is revoked."""

    refresh_token: str | None = Field(default=None, min_length=20, max_length=200)
