import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Ticket, User  # noqa: F401
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide an API client backed by an isolated in-memory database."""

    engine = create_async_engine("sqlite+aiosqlite://")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def create_tables() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        async def drop_tables() -> None:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
            await engine.dispose()

        asyncio.run(drop_tables())
