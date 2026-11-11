"""Підключення до бази: engine (пул з'єднань), фабрика сесій, базовий клас моделей, сесія на запит.

Стартовий код — `backend/core/database.py` зі стартового `production_bot`.
Рефакторинг уроку 38:
- адреса бази — зі змінної середовища `DATABASE_URL`; без неї — файл SQLite поруч із проєктом,
  щоб урок працював без PostgreSQL (ноутбук, Colab);
- `pool_size` / `max_overflow` — лише для PostgreSQL (у SQLite своя модель з'єднань);
- SQLite: `lower()` з підтримкою Unicode — інакше пошук без регістру не працює з кирилицею;
- `get_db` анотовано як `AsyncIterator[AsyncSession]` — це генератор, а не функція, що повертає сесію.
"""
import os
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# postgresql+asyncpg://news:news@localhost:5432/news_hub  — PostgreSQL (docker compose up -d db)
# sqlite+aiosqlite:///news_hub.db                          — файл поруч із проєктом
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///news_hub.db")


def make_engine(url: str = DATABASE_URL, echo: bool = False, **options: Any) -> AsyncEngine:
    if url.startswith("postgresql"):
        return create_async_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True, echo=echo, **options)
    sqlite_engine = create_async_engine(url, echo=echo, **options)
    event.listen(sqlite_engine.sync_engine, "connect", _unicode_lower)
    return sqlite_engine


def _unicode_lower(dbapi_connection: Any, _record: Any) -> None:
    """Вбудований lower() у SQLite знає лише латиницю: lower('ЗЕЛЕНСЬК') == 'ЗЕЛЕНСЬК'.
    Підміняємо його Python-версією — пошук без урахування регістру працює і з кирилицею, як у PostgreSQL."""
    dbapi_connection.create_function("lower", 1, lambda text: text.lower() if isinstance(text, str) else text,
                                     deterministic=True)


engine = make_engine()

# expire_on_commit=False — після commit() поля об'єкта доступні без нового SELECT
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    """Базовий клас моделей; Base.metadata — реєстр таблиць для Alembic і тестів."""


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI Depends: одна сесія (і одна транзакція) на HTTP-запит.

    Ендпоінт відпрацював без винятку → COMMIT; виняток → ROLLBACK; у будь-якому разі сесія закривається.
    """
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
