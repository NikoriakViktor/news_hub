"""Репозиторій новин: увесь SQL агрегатора в одному місці.

`BaseRepository` — `backend/repositories/base.py` зі стартового `production_bot` (загальний CRUD
для будь-якої моделі). `NewsRepository` має **ті самі методи, що `NewsStore` з уроку 37**
(`add_many`, `find`, `count`, `stats`, `clear`) — тому ендпоінти майже не змінились:
лише `store.find(...)` → `await repo.find(...)`.

Урок 43: аналіз LLM — `save_analysis`, `find_unanalyzed` (для пакетної задачі), фільтри й статистика
за темою (`ai_category`) і тональністю.
Урок 46: `SourceRepository` — RSS-джерела адміна.
Урок 47: `insert_new` (які саме новини нові — для сповіщень), `latest` (для /news у боті),
`SubscriptionRepository` — підписки чатів Telegram на ключові слова.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from .analysis import NewsAnalysis
from .db import Base
from .models import NewsItem
from .tables import NewsRow, SourceRow, SubscriptionRow

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


@dataclass(frozen=True)
class NewNews:
    """Щойно збережена новина — те, що потрібно для сповіщення (урок 47)."""
    id: int
    title: str
    url: str


def news_values(item: NewsItem) -> dict[str, Any]:
    """Перевірений NewsItem → значення стовпців таблиці."""
    return {"url": str(item.url), "title": item.title, "source": item.source, "lang": item.lang,
            "category": item.category, "published_time": item.published_time}


class NewsRepository(BaseRepository[NewsRow]):
    model = NewsRow

    async def add_many(self, items: Iterable[NewsItem]) -> int:
        """INSERT … ON CONFLICT (url) DO NOTHING: дублікати відсіює база; повертає, скільки додано."""
        return len(await self.insert_new(items))

    async def insert_new(self, items: Iterable[NewsItem]) -> list[NewNews]:
        """Те саме, але повертає саме нові новини (RETURNING лише вставлених рядків) — для сповіщень."""
        rows = [news_values(item) for item in items]
        if not rows:
            return []
        dialect = self._session.get_bind().dialect.name
        stmt = (postgresql.insert(NewsRow) if dialect == "postgresql" else sqlite.insert(NewsRow)) \
            .values(rows).on_conflict_do_nothing(index_elements=["url"]) \
            .returning(NewsRow.id, NewsRow.title, NewsRow.url)
        return [NewNews(id=row.id, title=row.title, url=row.url) for row in await self._session.execute(stmt)]

    async def latest(self, limit: int = 5) -> list[NewsRow]:
        """Найновіші за часом збору (id зростає разом із ним)."""
        stmt = select(NewsRow).order_by(NewsRow.id.desc()).limit(limit)
        return list((await self._session.scalars(stmt)).all())

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


class SubscriptionRepository(BaseRepository[SubscriptionRow]):
    """Підписки: (chat_id, keyword) унікальні — повторна підписка нічого не додає."""
    model = SubscriptionRow

    async def subscribe(self, chat_id: int, keyword: str) -> bool:
        """True — нова підписка; False — уже була."""
        dialect = self._session.get_bind().dialect.name
        insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
        stmt = insert(SubscriptionRow).values(chat_id=chat_id, keyword=keyword) \
            .on_conflict_do_nothing(index_elements=["chat_id", "keyword"]).returning(SubscriptionRow.id)
        return (await self._session.execute(stmt)).first() is not None

    async def unsubscribe(self, chat_id: int, keyword: str) -> bool:
        stmt = delete(SubscriptionRow).where(SubscriptionRow.chat_id == chat_id, SubscriptionRow.keyword == keyword) \
            .returning(SubscriptionRow.id)
        return (await self._session.execute(stmt)).first() is not None

    async def for_chat(self, chat_id: int) -> list[str]:
        stmt = select(SubscriptionRow.keyword).where(SubscriptionRow.chat_id == chat_id).order_by(SubscriptionRow.keyword)
        return list((await self._session.scalars(stmt)).all())

    async def by_chat(self) -> dict[int, list[str]]:
        """Усі підписки: чат → ключові слова (для розсилки після збору)."""
        result: dict[int, list[str]] = {}
        stmt = select(SubscriptionRow.chat_id, SubscriptionRow.keyword).order_by(SubscriptionRow.chat_id,
                                                                                   SubscriptionRow.keyword)
        for chat_id, keyword in await self._session.execute(stmt):
            result.setdefault(chat_id, []).append(keyword)
        return result

    async def remove_chat(self, chat_id: int) -> int:
        """Чат заблокував бота — його підписки більше не потрібні."""
        stmt = delete(SubscriptionRow).where(SubscriptionRow.chat_id == chat_id).returning(SubscriptionRow.id)
        return len((await self._session.execute(stmt)).all())
