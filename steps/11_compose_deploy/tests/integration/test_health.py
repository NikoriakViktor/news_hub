"""Урок 48: /health (процес живий) і /health/ready (база й Redis доступні).

Docker перевіряє /health (HEALTHCHECK образу), балансувальник і Compose — /health/ready.
Недоступну базу імітуємо SQLite-файлом у каталозі, якого немає; Redis — портом, де ніхто не слухає.
"""
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from news_hub.api import app
from news_hub.cache import get_redis
from news_hub.db import get_db, make_engine

MISSING_DB = "sqlite+aiosqlite:////nonexistent-dir/secret-name.db"


def break_database() -> None:
    factory = async_sessionmaker(make_engine(MISSING_DB), expire_on_commit=False)

    async def broken_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = broken_db


def break_redis() -> None:
    app.dependency_overrides[get_redis] = lambda: Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.5)


def test_ready_when_database_and_redis_answer(anon: TestClient) -> None:
    response = anon.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


def test_database_down_is_503_but_process_is_alive(anon: TestClient) -> None:
    break_database()
    response = anon.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "OperationalError", "redis": "ok"}
    assert "secret-name" not in response.text             # шлях/адреса бази — лише в журнал, не назовні
    assert anon.get("/health").status_code == 200         # liveness не залежить від бази: не перезапускати


def test_redis_down_is_503(anon: TestClient) -> None:
    break_redis()
    response = anon.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "checks": {"database": "ok", "redis": "ConnectionError"}}
