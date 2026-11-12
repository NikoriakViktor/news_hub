"""Таблиці прикладу: новини й журнал дій (audit). Дві таблиці — щоб Unit of Work мав що об'єднувати."""
from typing import Any

from sqlalchemy import String, event
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class NewsRow(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    views: Mapped[int] = mapped_column(default=0)


class AuditRow(Base):
    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(50))
    news_id: Mapped[int | None]


def fix_sqlite_transactions(engine: AsyncEngine) -> None:
    """Драйвер sqlite3/aiosqlite сам вирішує, коли слати BEGIN, і не шле його перед SAVEPOINT:
    RELEASE зовнішнього SAVEPOINT тоді робить COMMIT. Вимикаємо його логіку, BEGIN шле SQLAlchemy.
    Рецепт з документації SQLAlchemy («Serializable isolation / Savepoints / Transactional DDL»)."""

    @event.listens_for(engine.sync_engine, "connect")
    def _no_driver_transactions(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def _begin(conn: Any) -> None:
        conn.exec_driver_sql("BEGIN")
