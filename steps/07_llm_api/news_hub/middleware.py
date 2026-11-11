"""HTTP middleware агрегатора: код, що обгортає КОЖЕН запит — до ендпоінта і після нього.

Порядок (зовнішній → внутрішній), як їх реєструє api.py:
    request_context   — X-Request-ID, X-Process-Time, рядок журналу;
    rate_limit        — POST /api/scrape* і аналіз LLM: не більше N запитів за вікно з однієї адреси → 429;
    invalidate_cache  — успішний запис у новини → нова версія кешу (після COMMIT).

Rate limit — `RateLimitRepository` + `RateLimitMiddleware` зі стартового `ai_bot`.
Рефакторинг уроку 39:
- aiogram-middleware → HTTP-middleware FastAPI; ключ — адреса клієнта + дія, а не user_id Telegram;
- `INCR`, а потім окремий `EXPIRE` (якщо count == 1) → одна транзакція `INCR` + `EXPIRE … NX`:
  якщо процес упаде між двома командами, ключ без TTL заблокує клієнта назавжди;
- у старому docstring алгоритм названо «Sliding Window Counter», але це **фіксоване вікно**
  (лічильник обнуляється разом із ключем) — назву виправлено, різницю показано в уроці.
Урок 43: аналіз LLM коштує грошей і квоти — свій ліміт (`ANALYZE_RATE_LIMIT`), ключ `rate:analyze:<адреса>`.
"""
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from .cache import NewsCache, get_redis

logger = logging.getLogger("news_hub")

CallNext = Callable[[Request], Awaitable[Response]]

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "5"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))      # секунд
ANALYZE_RATE_LIMIT = int(os.getenv("ANALYZE_RATE_LIMIT", "10"))    # запитів до LLM за вікно


async def request_context(request: Request, call_next: CallNext) -> Response:
    """Найзовнішній шар: бачить увесь час обробки, зокрема інших middleware."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{elapsed_ms:.1f}ms"
    logger.info("%s %s %s → %s %.1f ms", request_id, request.method, request.url.path,
                response.status_code, elapsed_ms)
    return response


class RateLimiter:
    """Фіксоване вікно: лічильник на ключ, що живе RATE_LIMIT_WINDOW секунд."""

    def __init__(self, redis: Redis, limit: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW) -> None:
        self._redis, self.limit, self.window = redis, limit, window

    async def hit(self, client: str, action: str) -> tuple[bool, int, int]:
        """+1 до лічильника; повертає (дозволено?, скільки запитів у вікні, секунд до нового вікна)."""
        key = f"rate:{action}:{client}"
        async with self._redis.pipeline(transaction=True) as pipe:      # MULTI … EXEC: разом або ніяк
            pipe.incr(key)
            pipe.expire(key, self.window, nx=True)                        # TTL лише новому ключу
            pipe.ttl(key)
            count, _, ttl = await pipe.execute()
        return count <= self.limit, count, max(ttl, 0)


def limited_action(request: Request) -> str | None:
    """Яка «дорога» дія: scrape — завантаження сайту, analyze — виклик LLM; None — без ліміту."""
    path = request.url.path
    if request.method != "POST":
        return None
    if path.startswith("/api/scrape"):
        return "scrape"
    if path.endswith("/analyze") or path.startswith("/api/analyze"):
        return "analyze"
    return None


async def rate_limit(request: Request, call_next: CallNext) -> Response:
    action = limited_action(request)
    if action is None:
        return await call_next(request)
    limit = ANALYZE_RATE_LIMIT if action == "analyze" else RATE_LIMIT_REQUESTS
    limiter = RateLimiter(get_redis(request), limit=limit)
    client = request.client.host if request.client else "unknown"
    allowed, count, ttl = await limiter.hit(client, action)
    headers = {"X-RateLimit-Limit": str(limiter.limit),
               "X-RateLimit-Remaining": str(max(limiter.limit - count, 0))}
    if not allowed:
        logger.warning("rate limit %s: %s count=%s", action, client, count)
        return JSONResponse(status_code=429, headers={**headers, "Retry-After": str(ttl)},
                            content={"detail": f"забагато запитів: {limiter.limit} за {limiter.window} с; "
                                               f"спробуй через {ttl} с"})
    response = await call_next(request)
    response.headers.update(headers)
    return response


WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


async def invalidate_cache(request: Request, call_next: CallNext) -> Response:
    """Після успішного запису — нова версія кешу.

    Чому тут, а не в ендпоінті: COMMIT робить get_db (урок 38) уже ПІСЛЯ ендпоінта. Інвалідація в
    ендпоінті йшла б до COMMIT, і паралельний GET встиг би закешувати старі дані під новою версією.
    Middleware отримує відповідь, коли COMMIT уже відбувся (scope="function").
    """
    response = await call_next(request)
    path = request.url.path
    if (request.method in WRITE_METHODS and response.status_code < 400
            and (path.startswith("/api/news") or path == "/api/scrape")):
        await NewsCache(get_redis(request)).invalidate()
    return response
