"""Фікстури: кожен тест отримує і фейк, і справжню реалізацію (SQLite у пам'яті) — ті самі перевірки для обох."""
import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from news_app.repositories import InMemoryNewsRepository, NewsRepository, SqlNewsRepository
from news_app.tables import Base, fix_sqlite_transactions
from news_app.uow import FakeUnitOfWork, SqlUnitOfWork, UnitOfWork


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite://")


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    if TEST_DATABASE_URL.startswith("sqlite"):
        # SQLite у пам'яті живе, поки відкрите з'єднання → StaticPool: одне з'єднання на весь тест
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=StaticPool)
        fix_sqlite_transactions(engine)
    else:
        engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture(params=["memory", "sql"])
async def repo(request: pytest.FixtureRequest,
               session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[NewsRepository]:
    if request.param == "memory":
        yield InMemoryNewsRepository()
        return
    async with session_factory() as session:
        yield SqlNewsRepository(session)


@pytest.fixture(params=["fake", "sql"])
def uow(request: pytest.FixtureRequest, session_factory: async_sessionmaker[AsyncSession]) -> UnitOfWork:
    return FakeUnitOfWork() if request.param == "fake" else SqlUnitOfWork(session_factory)
