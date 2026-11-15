"""Create the database schema.

Usage::

    python -m scripts.init_db
"""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.db.session import create_engine, init_models


async def main() -> None:
    settings = Settings()
    engine = create_engine(settings)
    try:
        await init_models(engine)
        print(f"Database schema is up to date: {settings.database_url}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
