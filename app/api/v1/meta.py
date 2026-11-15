"""Metadata endpoints (skill catalog)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.analyzer.skills import SKILL_CATALOG
from app.api.deps import get_current_user
from app.db.models import User
from app.schemas.skill import SkillRead

router = APIRouter(tags=["meta"])


@router.get("/skills", response_model=list[SkillRead], summary="List supported skills")
async def list_skills(_user: User = Depends(get_current_user)) -> list[SkillRead]:
    return [SkillRead(name=skill.name, category=skill.category) for skill in SKILL_CATALOG]
