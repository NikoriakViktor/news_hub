"""Справжній get_db, а не його копія з conftest (урок 41).

Інтеграційні тести API підміняють get_db тестовою версією (dependency_overrides) — отже, самого get_db
вони не виконують ні разу (покриття: рядки 54–60 db.py червоні). Тут перевіряємо оригінал: підміняємо
лише фабрику сесій, на яку він посилається, — `news_hub.db.SessionFactory` (patch where used).
"""
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from news_hub import db
from news_hub.api import get_scrapers, get_session_factory
from news_hub.tables import NewsRow

@pytest_asyncio.fixture
async def factory(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = db.make_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    test_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "SessionFactory", test_factory)
    yield test_factory
    await engine.dispose()


def row(n: int) -> NewsRow:
    return NewsRow(title=f"Новина номер {n} для тесту", url=f"https://www.rbc.ua/ukr/news/{n}.html",
                   source="rbc.ua", lang="uk", category="Новини")


async def count(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as session:
        return (await session.scalar(select(func.count()).select_from(NewsRow))) or 0


@pytest.mark.asyncio
async def test_success_commits(factory: async_sessionmaker[AsyncSession]) -> None:
    dependency = db.get_db()                       # так його викликає FastAPI: до yield …
    session = await anext(dependency)
    session.add(row(1))
    with pytest.raises(StopAsyncIteration):        # … і після відповіді ендпоінта — код після yield
        await anext(dependency)
    assert await count(factory) == 1


@pytest.mark.asyncio
async def test_exception_rolls_back_and_propagates(factory: async_sessionmaker[AsyncSession]) -> None:
    dependency = db.get_db()
    session = await anext(dependency)
    session.add(row(1))
    await session.flush()                          # INSERT уже в базі, але в незавершеній транзакції
    with pytest.raises(RuntimeError, match="ендпоінт упав"):
        await dependency.athrow(RuntimeError("ендпоінт упав"))    # так FastAPI передає виняток у залежність
    assert await count(factory) == 0


def test_postgres_engine_gets_pool_settings() -> None:
    """Гілка PostgreSQL у make_engine: engine створюється без з'єднання — сервер для цього не потрібен."""
    engine = db.make_engine("postgresql+asyncpg://news:news@localhost:5432/news_hub")
    assert (engine.dialect.name, engine.pool.size()) == ("postgresql", 10)      # type: ignore[attr-defined]


def test_real_dependencies_point_at_real_objects() -> None:
    """Те, що тести завжди підміняють, хоч раз — без підміни."""
    assert get_session_factory() is db.SessionFactory
    assert set(get_scrapers()) == {"async", "sequential"}
