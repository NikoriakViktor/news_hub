"""Таблиця `news` — модель SQLAlchemy 2.0 (`Mapped` + `mapped_column`), як `models/user.py` у `production_bot`.

Дві моделі на одну новину, і це навмисно:
- `NewsItem` (Pydantic, models.py) — **перевірка** даних з парсера й тіла запиту;
- `NewsRow` (SQLAlchemy, тут) — **рядок таблиці**: id, унікальний url, час збору.

Урок 43: результат аналізу LLM — у тих самих рядках (`summary` … `analyzed_at`, міграція 0002).
Усі поля можуть бути NULL: новину зберігаємо одразу, аналізуємо пізніше (або ніколи).
Урок 46: таблиця `sources` — RSS-джерела, які додає адмін (міграція 0003).
Урок 47: таблиця `subscriptions` — ключові слова, на які чат Telegram підписався (міграція 0004).
"""
from datetime import datetime, time

from sqlalchemy import JSON, BigInteger, DateTime, String, Time, UniqueConstraint, func
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

    # Аналіз LLM (урок 43): NULL — ще не аналізували
    summary: Mapped[str | None] = mapped_column(String(300))
    ai_category: Mapped[str | None] = mapped_column(String(30), index=True)
    sentiment: Mapped[str | None] = mapped_column(String(10), index=True)
    keywords: Mapped[list[str] | None] = mapped_column(JSON)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<NewsRow id={self.id} lang={self.lang} title={self.title[:30]!r}>"


class SourceRow(Base):
    """RSS-джерело, яке додав адмін (урок 46). Адресу перевіряє safe_fetch — і при додаванні, і при кожному збиранні."""
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<SourceRow id={self.id} url={self.url!r}>"


class SubscriptionRow(Base):
    """Підписка чату Telegram на ключове слово (урок 47).

    Основа — `models/subscription.py` з `production_bot` (там підписка — тариф користувача); тут — пара
    «чат + слово». chat_id — BigInteger: id у Telegram бувають довшими за 32 біти (групи: -100…).
    """
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("chat_id", "keyword", name="uq_subscription_chat_keyword"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    keyword: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<SubscriptionRow chat_id={self.chat_id} keyword={self.keyword!r}>"
