"""Сповіщення підписників про нові новини. Урок 47.

Основа — `backend/workers/notifications.py` зі стартового `production_bot`: `while True` → вибірка
з бази → `bot.send_message` кожному → `except Exception: logger.warning`. Рефакторинг:
- не окремий нескінченний цикл, а виклик **після збору**, з тими новинами, які щойно з'явились у базі
  (`NewsRepository.insert_new`) — повторний збір тих самих новин нікого не сповіщає вдруге;
- одне повідомлення на чат з усіма збігами, а не по повідомленню на новину;
- ліміти Telegram (≈30 повідомлень за секунду на бота): пауза між чатами; 429 → чекаємо `retry_after`
  і пробуємо ще раз;
- користувач заблокував бота (403) → його підписки видаляються: інакше кожен збір стукав би в чат,
  який ніколи не відповість. Інші помилки — у звіт, розсилка решті триває.
"""
import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .bot.formatting import esc, link, matches, split_message
from .repository import NewNews, SubscriptionRepository

logger = logging.getLogger("news_hub")

SEND_PAUSE = 0.05            # секунд між повідомленнями: ~20 за секунду, нижче ліміту Telegram
MAX_NEWS_PER_CHAT = 20


@dataclass
class NotifyReport:
    chats: int = 0                                          # скільки чатів мали збіги
    sent: int = 0                                           # повідомлень надіслано
    blocked: list[int] = field(default_factory=list)        # чати, що заблокували бота (підписки видалено)
    failed: dict[int, str] = field(default_factory=dict)    # інші помилки: чат → опис


def build_messages(keywords: Sequence[str], news: Sequence[NewNews]) -> list[str]:
    """Новини, що збіглися з будь-яким ключовим словом чату → частини повідомлення (≤ 4096)."""
    found = [item for item in news if any(matches(keyword, item.title) for keyword in keywords)]
    if not found:
        return []
    lines = [f"🔔 Нові новини за підписками ({esc(', '.join(keywords))}):", ""]
    lines += [f"• {link(item.url, item.title)}" for item in found[:MAX_NEWS_PER_CHAT]]
    if len(found) > MAX_NEWS_PER_CHAT:
        lines.append(f"… і ще {len(found) - MAX_NEWS_PER_CHAT}")
    return split_message(lines)


async def _send(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text, disable_web_page_preview=True)
    except TelegramRetryAfter as error:                     # 429: Telegram каже, скільки чекати
        await asyncio.sleep(error.retry_after)
        await bot.send_message(chat_id, text, disable_web_page_preview=True)


async def notify_subscribers(bot: Bot, subscriptions: SubscriptionRepository,
                             news: Sequence[NewNews]) -> NotifyReport:
    """Розсилка після збору. COMMIT (видалення підписок заблокованих чатів) — справа того, хто викликав."""
    report = NotifyReport()
    if not news:
        return report
    for chat_id, keywords in (await subscriptions.by_chat()).items():
        messages = build_messages(keywords, news)
        if not messages:
            continue
        report.chats += 1
        try:
            for text in messages:
                await _send(bot, chat_id, text)
                report.sent += 1
                await asyncio.sleep(SEND_PAUSE)
        except TelegramForbiddenError:
            await subscriptions.remove_chat(chat_id)
            report.blocked.append(chat_id)
            logger.info("чат %s заблокував бота — підписки видалено", chat_id)
        except TelegramAPIError as error:
            report.failed[chat_id] = f"{type(error).__name__}: {error}"
            logger.warning("сповіщення в чат %s не надіслано: %s", chat_id, error)
    logger.info("сповіщення: чатів %s, повідомлень %s, заблокували %s, помилок %s",
                report.chats, report.sent, len(report.blocked), len(report.failed))
    return report


@dataclass
class Notifier:
    """Розсилка зі своєю сесією бази — для фонових задач API (після відповіді й COMMIT запиту)."""
    bot: Bot
    session_factory: async_sessionmaker[AsyncSession]

    async def __call__(self, news: Sequence[NewNews]) -> NotifyReport:
        async with self.session_factory() as session:
            report = await notify_subscribers(self.bot, SubscriptionRepository(session), news)
            await session.commit()                          # видалені підписки заблокованих чатів
        return report
