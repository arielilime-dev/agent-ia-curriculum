"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.analyzer.ai.base import AIProvider
from app.analyzer.ai.factory import build_ai_provider
from app.analyzer.pipeline import ResumeAnalysisPipeline
from app.api.middleware import RequestContextMiddleware
from app.api.router import api_router
from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.core.rate_limit import SlidingWindowRateLimiter
from app.db.session import create_engine, create_session_factory, init_models
from app.services.storage import Storage

logger = logging.getLogger(__name__)

API_DESCRIPTION = """
API REST para análise de currículos com IA.

**Recursos**
- Autenticação JWT com access token curto e refresh token rotativo.
- Upload de currículos em PDF, DOCX, TXT e Markdown com extração e parsing.
- Análise determinística (competências, experiência, formação, ATS) enriquecida por IA.
- Comparação com descrição de vaga, sugestões acionáveis e painel de métricas.

**Autenticação**: obtenha um token em `POST /api/v1/auth/login` (campo `username` = e-mail)
e envie `Authorization: Bearer <token>`.
"""


def create_app(
    settings: Settings | None = None,
    *,
    ai_provider: AIProvider | None = None,
) -> FastAPI:
    """Build a fully wired application instance (useful for tests and workers)."""
    resolved_settings = settings or Settings()
    configure_logging(resolved_settings.log_level)

    engine = create_engine(resolved_settings)
    session_factory = create_session_factory(engine)
    storage = Storage(resolved_settings.ensure_storage_dir())

    http_client: httpx.AsyncClient | None = None
    if ai_provider is None:
        if resolved_settings.ai_provider != "heuristic":
            http_client = httpx.AsyncClient(timeout=resolved_settings.ai_timeout_seconds)
        ai_provider = build_ai_provider(resolved_settings, http_client=http_client)
    pipeline = ResumeAnalysisPipeline(ai_provider)
    auth_rate_limiter = (
        SlidingWindowRateLimiter(resolved_settings.rate_limit_auth_per_minute, 60.0)
        if resolved_settings.rate_limit_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if resolved_settings.auto_create_tables:
            await init_models(engine)
        try:
            yield
        finally:
            await engine.dispose()
            if http_client is not None:
                await http_client.aclose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "Resume Analyzer", "email": "contato@resumeanalyzer.com.br"},
        license_info={"name": "MIT"},
    )

    app.state.settings = resolved_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.storage = storage
    app.state.pipeline = pipeline
    app.state.ai_provider = ai_provider
    app.state.http_client = http_client
    app.state.auth_rate_limiter = auth_rate_limiter

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_payload(),
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed",
                "code": "validation_error",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Database integrity error: %s", exc)
        return JSONResponse(
            status_code=409,
            content={"detail": "The request conflicts with existing data", "code": "conflict"},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "code": "internal_error"},
        )

    app.include_router(api_router, prefix=resolved_settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, Any]:
        return {
            "name": resolved_settings.app_name,
            "version": resolved_settings.app_version,
            "environment": resolved_settings.environment,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "api": resolved_settings.api_v1_prefix,
        }

    return app


async def initialize_database(app: FastAPI) -> None:
    """Create tables for an app instance (used by tests and scripts)."""
    await init_models(app.state.engine)


app = create_app()


def run() -> None:  # pragma: no cover - console entrypoint
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
