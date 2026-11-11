"""Збирання бота: Bot, Dispatcher, middleware, роутер, меню команд. Урок 47.

Основа — `app/bot.py` з `ai_bot` (фабрики `create_bot` / `create_dispatcher`, `set_bot_commands`) і
`backend/app.py` зі стартового `production_bot`. Рефакторинг:
- `TelegramAPIServer.from_base(api_url)`: бот ходить на двійник Telegram або локальний Bot API server;
  без `api_url` — на api.telegram.org, як раніше;
- залежності — параметрами фабрики (база, Redis, LLM, адміни), а не глобальним `config`: ті самі фабрики
  збирають бота для webhook у FastAPI, для polling і для тестів;
- роутер — новий на кожен диспетчер (`handlers.build_router()`): aiogram не дає підключити один Router
  до двох Dispatcher, а в старому коді роутер був змінною модуля.
"""
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..llm import LLMClient
from . import handlers
from .middlewares import InjectMiddleware, RateLimitMiddleware

BOT_RATE_LIMIT, BOT_RATE_WINDOW = 20, 60           # повідомлень від одного користувача за хвилину

COMMANDS = [
    BotCommand(command="news", description="Останні новини"),
    BotCommand(command="digest", description="Дайджест з аналізом LLM"),
    BotCommand(command="subscribe", description="Підписатися на слово"),
    BotCommand(command="subscriptions", description="Мої підписки"),
    BotCommand(command="help", description="Допомога"),
]


def create_bot(token: str, api_url: str | None = None) -> Bot:
    session = AiohttpSession(api=TelegramAPIServer.from_base(api_url)) if api_url else None
    return Bot(token=token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher(session_factory: async_sessionmaker[AsyncSession], redis: Redis, llm: LLMClient | None,
                      admin_ids: frozenset[int] = frozenset()) -> Dispatcher:
    dp = Dispatcher()
    dp.message.outer_middleware(RateLimitMiddleware(redis, BOT_RATE_LIMIT, BOT_RATE_WINDOW))
    dp.message.middleware(InjectMiddleware(session_factory, redis, llm, admin_ids))
    dp.include_router(handlers.build_router())
    return dp


async def set_commands(bot: Bot) -> None:
    """Меню команд (кнопка ☰ у Telegram). На обробку команд не впливає."""
    await bot.set_my_commands(COMMANDS)
