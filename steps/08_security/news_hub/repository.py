"""Репозиторій новин: увесь SQL агрегатора в одному місці.

`BaseRepository` — `backend/repositories/base.py` зі стартового `production_bot` (загальний CRUD
для будь-якої моделі). `NewsRepository` має **ті самі методи, що `NewsStore` з уроку 37**
(`add_many`, `find`, `count`, `stats`, `clear`) — тому ендпоінти майже не змінились:
лише `store.find(...)` → `await repo.find(...)`.

Урок 43: аналіз LLM — `save_analysis`, `find_unanalyzed` (для пакетної задачі), фільтри й статистика
за темою (`ai_category`) і тональністю.
Урок 46: `SourceRepository` — RSS-джерела адміна.
"""
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from .analysis import NewsAnalysis
from .db import Base
from .models import NewsItem
from .tables import NewsRow, SourceRow

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, obj_id: int) -> ModelT | None:
        return await self._session.get(self.model, obj_id)

    async def add(self, obj: ModelT) -> ModelT:
        self._session.add(obj)
        await self._session.flush()      # INSERT зараз, щоб отримати id і помилки обмежень; COMMIT — у get_db
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self._session.delete(obj)
        await self._session.flush()

    async def count(self) -> int:
        return (await self._session.execute(select(func.count()).select_from(self.model))).scalar_one()


def news_values(item: NewsItem) -> dict[str, Any]:
    """Перевірений NewsItem → значення стовпців таблиці."""
    return {"url": str(item.url), "title": item.title, "source": item.source, "lang": item.lang,
            "category": item.category, "published_time": item.published_time}


class NewsRepository(BaseRepository[NewsRow]):
    model = NewsRow

    async def add_many(self, items: Iterable[NewsItem]) -> int:
        """INSERT … ON CONFLICT (url) DO NOTHING: дублікати відсіює база; повертає, скільки додано."""
        rows = [news_values(item) for item in items]
        if not rows:
            return 0
        dialect = self._session.get_bind().dialect.name
        stmt = (postgresql.insert(NewsRow) if dialect == "postgresql" else sqlite.insert(NewsRow)) \
            .values(rows).on_conflict_do_nothing(index_elements=["url"]).returning(NewsRow.id)
        return len((await self._session.execute(stmt)).all())

    async def create(self, item: NewsItem) -> NewsRow:
        """Одна новина; такий самий url уже є → IntegrityError (ловить ендпоінт → 409)."""
        return await self.add(NewsRow(**news_values(item)))

    async def find(self, *, skip: int = 0, limit: int = 50, category: str = "", source: str = "",
                   lang: str = "", ai_category: str = "", sentiment: str = "") -> list[NewsRow]:
        stmt = select(NewsRow).order_by(NewsRow.id).offset(skip).limit(limit)
        if ai_category:
            stmt = stmt.where(NewsRow.ai_category == ai_category)
        if sentiment:
            stmt = stmt.where(NewsRow.sentiment == sentiment)
        if category:
            stmt = stmt.where(NewsRow.category == category)
        if source:
            stmt = stmt.where(NewsRow.source == source)
        if lang:
            stmt = stmt.where(NewsRow.lang == lang)
        return list((await self._session.scalars(stmt)).all())

    async def search(self, q: str, limit: int = 20) -> list[NewsRow]:
        """Заголовки, що містять q без урахування регістру: WHERE lower(title) LIKE lower('%' || :q || '%').

        q — параметр запиту, а не частина SQL (урок 29); autoescape: % і _ у q — звичайні символи.
        """
        stmt = select(NewsRow).where(NewsRow.title.icontains(q, autoescape=True)).order_by(NewsRow.id).limit(limit)
        return list((await self._session.scalars(stmt)).all())

    async def stats(self) -> dict[str, dict[str, int]]:
        """SELECT <поле>, count(*) … GROUP BY <поле> — для категорій, мов і джерел."""
        result: dict[str, dict[str, int]] = {}
        for field in ("category", "lang", "source", "ai_category", "sentiment"):
            column = getattr(NewsRow, field)
            rows = await self._session.execute(       # NULL (ще не аналізовані) — не рахуємо
                select(column, func.count()).where(column.is_not(None)).group_by(column)
                .order_by(func.count().desc(), column))
            result[field] = {value: count for value, count in rows}
        return result

    async def find_unanalyzed(self, limit: int) -> list[NewsRow]:
        stmt = select(NewsRow).where(NewsRow.analyzed_at.is_(None)).order_by(NewsRow.id).limit(limit)
        return list((await self._session.scalars(stmt)).all())

    async def save_analysis(self, row: NewsRow, analysis: NewsAnalysis) -> datetime:
        """Записує аналіз у рядок новини; повертає час аналізу."""
        row.summary, row.ai_category, row.sentiment = analysis.summary, analysis.category, analysis.sentiment
        row.keywords = list(analysis.keywords)
        row.analyzed_at = analyzed_at = datetime.now(timezone.utc)
        await self._session.flush()
        return analyzed_at

    async def clear(self) -> int:
        return len((await self._session.execute(delete(NewsRow).returning(NewsRow.id))).all())



class SourceRepository(BaseRepository[SourceRow]):
    model = SourceRow

    async def create(self, url: str, name: str) -> SourceRow:
        """Такий самий url уже є → IntegrityError (ловить ендпоінт → 409)."""
        return await self.add(SourceRow(url=url, name=name))

    async def all(self) -> list[SourceRow]:
        return list((await self._session.scalars(select(SourceRow).order_by(SourceRow.id))).all())
