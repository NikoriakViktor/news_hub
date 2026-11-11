"""Middleware бота (урок 47) — з `app/middlewares/` стартового `ai_bot`.

Update → [outer: RateLimitMiddleware] → роутери → [inner: InjectMiddleware] → handler.

- `RateLimitMiddleware` — той самий `RateLimiter` (Redis INCR + EXPIRE NX), що й rate limit API в уроці 39,
  ключ `rate:bot:tg<user_id>`. Відповідь про ліміт — один раз за вікно, а не на кожне повідомлення.
- `InjectMiddleware` — «Depends для бота»: на кожен update **своя** сесія бази, як `get_db` у FastAPI;
  COMMIT після handler. У стартовому `ai_bot` у handlers ішов один спільний репозиторій на Redis — з базою
  так не можна: сесія SQLAlchemy не для одночасних update.
"""
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..llm import CircuitBreaker, GuardedLLM, LLMClient
from ..middleware import RateLimiter
from ..repository import NewsRepository, SubscriptionRepository

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, limit: int, window: int) -> None:
        self._limiter = RateLimiter(redis, limit=limit, window=window)

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if not isinstance(event, Message) or event.from_user is None:
            return await handler(event, data)
        allowed, count, ttl = await self._limiter.hit(f"tg{event.from_user.id}", "bot")
        if allowed:
            return await handler(event, data)
        if count == self._limiter.limit + 1:              # лише перше перевищення — далі мовчимо
            await event.answer(f"⏳ Забагато запитів: {self._limiter.limit} за {self._limiter.window} с. "
                               f"Спробуй через {ttl} с.")
        return None


class InjectMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], redis: Redis,
                 llm: LLMClient | None, admin_ids: frozenset[int]) -> None:
        self._factory, self._redis, self._llm, self._admin_ids = session_factory, redis, llm, admin_ids

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self._factory() as session:
            data["news"] = NewsRepository(session)
            data["subscriptions"] = SubscriptionRepository(session)
            data["redis"] = self._redis
            data["llm"] = GuardedLLM(self._llm, CircuitBreaker(self._redis)) if self._llm else None
            data["admin_ids"] = self._admin_ids
            result = await handler(event, data)
            await session.commit()
            return result
