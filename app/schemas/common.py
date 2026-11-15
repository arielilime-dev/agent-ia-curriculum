"""Shared response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Message(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    """Error envelope returned by the global exception handlers."""

    detail: str
    code: str
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
