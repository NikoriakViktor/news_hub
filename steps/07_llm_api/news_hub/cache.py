"""Redis для агрегатора: клієнт і кеш стрічки (cache-aside з уроку 30).

Клієнт — `backend/core/redis.py` зі стартового `production_bot`.
Рефакторинг уроку 39:
- замість глобальної змінної `_redis_pool` — клієнт у `app.state`, створюється в `lifespan`, дістається
  через `Depends(get_redis)` (так його можна підмінити в тестах);
- `REDIS_URL=fakeredis://` — Redis у пам'яті процесу (пакет fakeredis) для тестів і ноутбука без сервера.

Інвалідація — через **версію**: ключі кешу містять номер `news:version`; будь-який запис у новини
збільшує версію (`INCR`), і старі ключі просто перестають читатися, а TTL їх прибирає.
Не треба шукати й видаляти ключі за шаблоном (`KEYS news:*` блокує Redis на великих базах).
"""
import hashlib
import json
import os
from typing import Any

from fastapi import Request
from redis.asyncio import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def make_redis(url: str = REDIS_URL) -> "Redis":
    if url.startswith("fakeredis://"):                 # лише для тестів і ноутбука
        import fakeredis
        return fakeredis.FakeAsyncRedis(decode_responses=True)
    return Redis.from_url(url, decode_responses=True)


def get_redis(request: Request) -> "Redis":
    redis: Redis = request.app.state.redis
    return redis


def _text(value: str | bytes | None) -> str | None:
    """decode_responses=True повертає str; типи redis-py допускають і bytes."""
    return value.decode() if isinstance(value, bytes) else value


class NewsCache:
    """Cache-aside: GET → є (hit) — віддати; немає (miss) — порахувати, SET з TTL, віддати."""

    TTL = 60                        # секунд: скільки стрічка може «відставати» від бази
    VERSION_KEY = "news:version"

    def __init__(self, redis: "Redis") -> None:
        self._redis = redis

    async def key(self, name: str, params: dict[str, Any]) -> str:
        version = _text(await self._redis.get(self.VERSION_KEY)) or "0"
        digest = hashlib.sha1(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
        return f"news:v{version}:{name}:{digest}"

    async def get(self, key: str) -> str | None:
        return _text(await self._redis.get(key))

    async def set(self, key: str, payload: str) -> None:
        await self._redis.set(key, payload, ex=self.TTL)

    async def invalidate(self) -> int:
        """Нова версія — усі старі ключі кешу більше не читаються."""
        version: int = await self._redis.incr(self.VERSION_KEY)
        return version
