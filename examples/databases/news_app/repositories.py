"""Репозиторій новин: контракт (Protocol), реалізація на SQLAlchemy і фейк у пам'яті для тестів.

Обидві реалізації проходять ті самі контрактні тести (tests/test_contract.py): фейк, що поводиться
інакше за справжній репозиторій, дає зелені тести й червоний продакшн.
"""
from dataclasses import dataclass, replace
from itertools import count
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .tables import NewsRow


@dataclass(frozen=True)
class News:
    """Те, що бачить решта програми: не рядок ORM, а звичайний об'єкт без сесії й лінивих зв'язків."""
    id: int
    url: str
    title: str
    views: int = 0


class DuplicateUrl(Exception):
    """Новина з таким url уже є. Обидві реалізації кидають саме його, а не IntegrityError."""


class NewsRepository(Protocol):
    async def add(self, url: str, title: str) -> News: ...
    async def get(self, news_id: int) -> News | None: ...
    async def latest(self, limit: int) -> list[News]: ...
    async def add_view(self, news_id: int) -> None: ...


class SqlNewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, url: str, title: str) -> News:
        row = NewsRow(url=url, title=title)
        try:
            async with self._session.begin_nested():     # SAVEPOINT: дубль не ламає всю транзакцію
                self._session.add(row)
        except IntegrityError as exc:
            raise DuplicateUrl(url) from exc
        return _to_news(row)

    async def get(self, news_id: int) -> News | None:
        row = await self._session.get(NewsRow, news_id)
        return _to_news(row) if row else None

    async def latest(self, limit: int) -> list[News]:
        rows = await self._session.scalars(select(NewsRow).order_by(NewsRow.id.desc()).limit(limit))
        return [_to_news(row) for row in rows]

    async def add_view(self, news_id: int) -> None:
        # атомарно в базі: UPDATE … SET views = views + 1; об'єкт у сесії SQLAlchemy оновить сама
        await self._session.execute(update(NewsRow).where(NewsRow.id == news_id).values(views=NewsRow.views + 1))


def _to_news(row: NewsRow) -> News:
    return News(id=row.id, url=row.url, title=row.title, views=row.views or 0)


class InMemoryNewsRepository:
    def __init__(self) -> None:
        self.rows: dict[int, News] = {}
        self._ids = count(1)

    async def add(self, url: str, title: str) -> News:
        if any(item.url == url for item in self.rows.values()):
            raise DuplicateUrl(url)
        item = News(id=next(self._ids), url=url, title=title)
        self.rows[item.id] = item
        return item

    async def get(self, news_id: int) -> News | None:
        return self.rows.get(news_id)

    async def latest(self, limit: int) -> list[News]:
        return sorted(self.rows.values(), key=lambda item: item.id, reverse=True)[:limit]

    async def add_view(self, news_id: int) -> None:
        if news_id in self.rows:
            self.rows[news_id] = replace(self.rows[news_id], views=self.rows[news_id].views + 1)
