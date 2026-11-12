"""Спільне для демо: дві таблиці зі зв'язком, адреса бази, лічильник SQL-запитів.

DATABASE_URL не задано — файл SQLite у тимчасовій папці (нічого не лишається в репозиторії).
PostgreSQL: DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres
"""
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, event, func, insert
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def database_url() -> str:
    return os.getenv("DATABASE_URL") or f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/demo.db"


class Base(AsyncAttrs, DeclarativeBase):
    """AsyncAttrs додає obj.awaitable_attrs.<зв'язок> — явне ліниве завантаження через await."""


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    news: Mapped[list["News"]] = relationship(back_populates="source", order_by="News.id")

    def __repr__(self) -> str:
        return f"Source({self.name!r})"


class News(Base):
    __tablename__ = "news"
    __table_args__ = (CheckConstraint("views >= 0", name="views_not_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    lang: Mapped[str] = mapped_column(String(2))
    views: Mapped[int] = mapped_column(default=0)
    scraped_at: Mapped[datetime] = mapped_column(server_default=func.now())
    source: Mapped[Source] = relationship(back_populates="news")

    def __repr__(self) -> str:
        return f"News(id={self.id}, views={self.views})"


SOURCES = ["rbc.ua", "ukrinform", "pravda", "suspilne"]
NEWS = [  # (номер джерела, заголовок, мова, перегляди)
    (1, "Гривня зміцнилася на міжбанку", "uk", 540), (1, "Курс евро снизился", "ru", 320),
    (2, "Укрзалізниця призначила нові поїзди", "uk", 980), (3, "Енергетики відновили живлення", "uk", 760),
    (1, "Цены на топливо выросли", "ru", 450), (2, "Kyiv hosts a tech summit", "en", 610),
    (3, "Графіки відключень на тиждень", "uk", 1250), (1, "Нацбанк зберіг облікову ставку", "uk", 280),
    (2, "Стартап зі Львова залучив інвестиції", "uk", 390),
]


async def fresh_engine(**options: Any) -> AsyncEngine:
    """Engine з порожніми таблицями й тими самими 4 джерелами та 9 новинами."""
    engine = create_async_engine(database_url(), **options)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(insert(Source), [{"name": name} for name in SOURCES])
        await conn.execute(insert(News), [
            {"source_id": s, "url": f"https://example.com/{i}", "title": t, "lang": lang, "views": v}
            for i, (s, t, lang, v) in enumerate(NEWS, start=1)])
    return engine


@contextmanager
def count_queries(engine: AsyncEngine, show: bool = False) -> Iterator[list[str]]:
    """Збирає SQL, який engine відправив у базу (як echo=True, але в список)."""
    statements: list[str] = []

    def before(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool) -> None:
        statements.append(" ".join(statement.split()))
        if show:
            print("      SQL:", statements[-1][:150])

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)


def dialect(engine: AsyncEngine) -> str:
    return engine.dialect.name
