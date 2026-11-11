"""Тестова база й Redis: окремі на кожен тест; клієнти `client` (TestClient) і `aclient` (httpx.AsyncClient).

Урок 46: запис — лише адміну. `client` і `aclient` надсилають токен адміна (так тести уроків 37–43 перевіряють
те саме, що й раніше); `anon` — клієнт без токена, як будь-хто в інтернеті.

База — SQLite у пам'яті, таблиці з Base.metadata (без Alembic); Redis — fakeredis у пам'яті процесу.
Ті самі тести на справжніх серверах:
    TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test \
    TEST_REDIS_URL=redis://localhost:6379/15 pytest
"""
import os

os.environ["REDIS_URL"] = os.getenv("TEST_REDIS_URL", "fakeredis://")      # до імпорту news_hub
from news_hub.security import hash_password

# Урок 46: налаштування адміна й webhook для тестів — явні тестові значення, не з .env
ADMIN_PASSWORD = "test-admin-password"
os.environ.update({
    "JWT_SECRET": "test-jwt-secret-" + "x" * 32,
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD_HASH": hash_password(ADMIN_PASSWORD, rounds=4),    # 4 раунди — швидко; у проді 12
    "WEBHOOK_SECRET": "test-webhook-secret-" + "y" * 32,
})
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from news_hub.api import app, get_llm_client, get_scrapers, get_session_factory
from news_hub.db import Base, get_db, make_engine
from news_hub.llm import FakeLLM
from news_hub.parser import RawNews
from news_hub.scraper import PageResult, ScrapeOutcome
from news_hub.security import create_access_token, load_admin_settings


def admin_headers() -> dict[str, str]:
    settings = load_admin_settings()
    assert settings is not None
    return {"Authorization": f"Bearer {create_access_token(settings, 'admin')}"}

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


class TestDatabase:
    """Тестова база + підміна залежностей застосунку. Спільне для `client` (sync) і `aclient` (async)."""

    def __init__(self) -> None:
        # SQLite у пам'яті живе, поки відкрите з'єднання → StaticPool: одне з'єднання на весь тест
        extra = {"poolclass": StaticPool} if TEST_DATABASE_URL.startswith("sqlite") else {}
        self.engine = make_engine(TEST_DATABASE_URL, **extra)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    async def create_tables(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    async def get_db(self) -> AsyncIterator[AsyncSession]:       # той самий контракт, що news_hub.db.get_db
        async with self.factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def install(self) -> None:
        app.dependency_overrides[get_db] = self.get_db
        app.dependency_overrides[get_session_factory] = lambda: self.factory   # фонові задачі — теж у тестову базу
        app.dependency_overrides[get_scrapers] = lambda: {"async": fake_scraper, "sequential": fake_scraper}


@pytest.fixture
def anon() -> Iterator[TestClient]:
    """Урок 46: клієнт без токена — як будь-хто в інтернеті."""
    db = TestDatabase()
    db.install()
    with TestClient(app) as c:
        app.state.llm = FakeLLM()               # урок 43: навіть з GEMINI_API_KEY у середовищі — без платних викликів
        c.portal.call(db.create_tables)         # у циклі подій застосунку, де працюватиме engine
        c.portal.call(app.state.redis.flushdb)  # чистий Redis (для TEST_REDIS_URL — окрема база 15)
        yield c
        c.portal.call(db.engine.dispose)
    app.dependency_overrides.clear()


@pytest.fixture
def client(anon: TestClient) -> TestClient:
    """Синхронний клієнт адміна: застосунок крутиться у своєму потоці й циклі подій (portal)."""
    anon.headers.update(admin_headers())
    return anon


@pytest_asyncio.fixture
async def aclient() -> AsyncIterator[httpx.AsyncClient]:
    """Асинхронний клієнт (урок 41): тест і застосунок — в одному циклі подій, без portal.

    ASGITransport не запускає lifespan — запускаємо його самі, щоб з'явився app.state.redis.
    """
    db = TestDatabase()
    db.install()
    async with app.router.lifespan_context(app):
        app.state.llm = FakeLLM()
        await db.create_tables()
        await app.state.redis.flushdb()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=admin_headers()) as c:
            yield c
        await db.engine.dispose()
    app.dependency_overrides.clear()


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    """Урок 43: клієнт LLM для API — FakeLLM зі сценарієм: fake_llm.replies.extend([...]); виклики — fake_llm.calls."""
    fake = FakeLLM()
    app.dependency_overrides[get_llm_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_client, None)
