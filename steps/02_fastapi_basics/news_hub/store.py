"""Сховище новин у пам'яті процесу.

Рефакторинг уроку 37: у прототипі `news_dashboard` ендпоінти самі ходили в MongoDB
(`db.news.update_one(..., upsert=True)`, `db.news.find(query)`). Тут той самий контракт
винесено в клас `NewsStore`, а ендпоінти отримують його через `Depends`.
Урок 38 замінить цей клас на SQLAlchemy — з тими самими методами.
"""
from collections import Counter
from collections.abc import Iterable

from .models import NewsItem


class NewsStore:
    def __init__(self) -> None:
        self._items: dict[str, NewsItem] = {}      # url → новина: той самий url двічі не збережеться

    def add_many(self, items: Iterable[NewsItem]) -> int:
        """Додає лише нові (як `$setOnInsert` + `upsert` у Mongo); повертає, скільки додано."""
        saved = 0
        for item in items:
            key = str(item.url)
            if key not in self._items:
                self._items[key] = item
                saved += 1
        return saved

    def find(self, *, skip: int = 0, limit: int = 50, category: str = "", source: str = "",
             lang: str = "") -> list[NewsItem]:
        found = [item for item in self._items.values()
                 if (not category or item.category == category)
                 and (not source or item.source == source)
                 and (not lang or item.lang == lang)]
        return found[skip:skip + limit]

    def count(self) -> int:
        return len(self._items)

    def stats(self) -> dict[str, dict[str, int]]:
        """Скільки новин у кожній категорії, мові й джерелі."""
        items = self._items.values()
        return {field: dict(Counter(getattr(item, field) for item in items).most_common())
                for field in ("category", "lang", "source")}

    def clear(self) -> int:
        deleted = len(self._items)
        self._items.clear()
        return deleted
