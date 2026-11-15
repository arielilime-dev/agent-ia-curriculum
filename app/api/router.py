"""Versioned API router (``/api/v1``)."""

from fastapi import APIRouter

from app.api.v1 import analyses, auth, health, meta, resumes, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(resumes.router)
api_router.include_router(analyses.router)
api_router.include_router(meta.router)
