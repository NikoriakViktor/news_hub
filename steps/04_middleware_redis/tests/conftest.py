"""Тестова база й Redis: окремі на кожен тест.

База — SQLite у пам'яті, таблиці з Base.metadata (без Alembic); Redis — fakeredis у пам'яті процесу.
Ті самі тести на справжніх серверах:
    TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test \
    TEST_REDIS_URL=redis://localhost:6379/15 pytest
"""
import os

os.environ["REDIS_URL"] = os.getenv("TEST_REDIS_URL", "fakeredis://")      # до імпорту news_hub
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from news_hub.api import app, get_scrapers, get_session_factory
from news_hub.db import Base, get_db, make_engine
from news_hub.parser import RawNews
from news_hub.scraper import PageResult, ScrapeOutcome

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite://")

FAKE_NEWS: list[RawNews] = [
    {"title": "Уряд затвердив новий бюджет на рік", "url": "https://www.rbc.ua/ukr/news/budget-1.html",
     "category": "", "description": "", "datetime": "10:30"},
    {"title": "Коротко", "url": "https://www.rbc.ua/ukr/news/short-2.html",
     "category": "", "description": "", "datetime": ""},
]


async def fake_scraper(pages: list[str] | None) -> ScrapeOutcome:
    page = PageResult(url=(pages or ["https://www.rbc.ua/ukr/news/"])[0], start=0.0, end=0.1, count=2)
    return ScrapeOutcome(pages=[page], news=FAKE_NEWS, total_time=0.1)


@pytest.fixture
def client() -> Iterator[TestClient]:
    # SQLite у пам'яті живе, поки відкрите з'єднання → StaticPool: одне з'єднання на весь тест
    extra = {"poolclass": StaticPool} if TEST_DATABASE_URL.startswith("sqlite") else {}
    engine = make_engine(TEST_DATABASE_URL, **extra)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def create_tables() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    async def test_db() -> AsyncIterator[AsyncSession]:       # той самий контракт, що get_db
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_session_factory] = lambda: factory       # фонові задачі — теж у тестову базу
    app.dependency_overrides[get_scrapers] = lambda: {"async": fake_scraper, "sequential": fake_scraper}
    with TestClient(app) as c:
        c.portal.call(create_tables)            # у циклі подій застосунку, де працюватиме engine
        c.portal.call(app.state.redis.flushdb)  # чистий Redis (для TEST_REDIS_URL — окрема база 15)
        yield c
        c.portal.call(engine.dispose)
    app.dependency_overrides.clear()
