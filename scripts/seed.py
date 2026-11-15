"""Seed a demo account, resume and analysis.

Usage::

    python -m scripts.seed

The credentials are printed to stdout and are meant for local development only.
"""

from __future__ import annotations

import asyncio

from app.analyzer.ai.heuristic import HeuristicProvider
from app.analyzer.pipeline import ResumeAnalysisPipeline
from app.core.config import Settings
from app.db.models import Resume, User
from app.db.session import create_engine, create_session_factory, init_models
from app.services.analysis_service import create_analysis
from app.services.auth_service import register_user
from app.services.resume_service import create_resume
from app.services.storage import Storage
from sqlalchemy import select

DEMO_EMAIL = "demo@resumeanalyzer.com.br"
DEMO_PASSWORD = "DemoPass123"
DEMO_NAME = "Usuária Demonstração"

DEMO_RESUME = """Usuária Demonstração
Desenvolvedora Backend Sênior
demo@resume-analyzer.local | (11) 99999-0000 | São Paulo - SP
linkedin.com/in/demo | github.com/demo

RESUMO
Desenvolvedora backend com 7 anos de experiência em Python, FastAPI e arquitetura de microsserviços.

EXPERIÊNCIA PROFISSIONAL
Tech Corp — Desenvolvedora Backend Sênior
01/2021 - Atual
- Desenvolvi APIs REST com Python, FastAPI e PostgreSQL
- Liderei equipe de 5 pessoas e reduzi a latência em 40%
Fintech XYZ — Desenvolvedora Backend
03/2018 - 12/2020
- Implementei microsserviços com Docker e Kubernetes na AWS

FORMAÇÃO ACADÊMICA
Bacharelado em Ciência da Computação — Universidade de São Paulo
2014 - 2017

HABILIDADES
Python, FastAPI, SQL, PostgreSQL, Docker, Kubernetes, AWS, Git, Redis

IDIOMAS
Português - Nativo
Inglês - Avançado
"""

DEMO_JOB = """Vaga: Desenvolvedor(a) Backend Sênior

Requisitos:
- 5+ anos de experiência com Python e FastAPI
- Sólida experiência com PostgreSQL, Docker e Kubernetes
- Vivência com AWS e mensageria (Kafka)
- Inglês avançado

Responsabilidades:
- Desenvolver e evoluir APIs REST de alta disponibilidade
- Atuar em arquitetura de microsserviços
- Mentorar pessoas desenvolvedoras júnior
"""


async def main() -> None:
    settings = Settings()
    engine = create_engine(settings)
    await init_models(engine)
    session_factory = create_session_factory(engine)
    storage = Storage(settings.ensure_storage_dir())

    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = await register_user(
                session,
                settings,
                email=DEMO_EMAIL,
                full_name=DEMO_NAME,
                password=DEMO_PASSWORD,
            )
            exists = await session.scalar(select(Resume.id).where(Resume.user_id == user.id))
            if exists is None:
                resume = await create_resume(
                    session,
                    settings,
                    storage,
                    user,
                    filename="curriculo-demo.txt",
                    content_type="text/plain",
                    data=DEMO_RESUME.encode("utf-8"),
                    title="Currículo demo",
                )
                analysis = await create_analysis(
                    session,
                    ResumeAnalysisPipeline(HeuristicProvider()),
                    user,
                    resume_id=resume.id,
                    job_description=DEMO_JOB,
                    job_title="Desenvolvedor(a) Backend Sênior",
                )
                print(f"Demo analysis created with score {analysis.overall_score}")
        print(f"Demo account: {DEMO_EMAIL} / {DEMO_PASSWORD}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
