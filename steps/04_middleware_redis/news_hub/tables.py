"""Таблиця `news` — модель SQLAlchemy 2.0 (`Mapped` + `mapped_column`), як `models/user.py` у `production_bot`.

Дві моделі на одну новину, і це навмисно:
- `NewsItem` (Pydantic, models.py) — **перевірка** даних з парсера й тіла запиту;
- `NewsRow` (SQLAlchemy, тут) — **рядок таблиці**: id, унікальний url, час збору.
"""
from datetime import datetime, time

from sqlalchemy import DateTime, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class NewsRow(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)    # унікальність гарантує база, а не код
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(100), index=True)
    lang: Mapped[str] = mapped_column(String(2), index=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    published_time: Mapped[time | None] = mapped_column(Time)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<NewsRow id={self.id} lang={self.lang} title={self.title[:30]!r}>"
