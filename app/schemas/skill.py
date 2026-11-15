"""Skill catalog schema."""

from __future__ import annotations

from pydantic import BaseModel


class SkillRead(BaseModel):
    name: str
    category: str
