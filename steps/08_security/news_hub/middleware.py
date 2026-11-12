"""HTTP middleware агрегатора: код, що обгортає КОЖЕН запит — до ендпоінта і після нього.

Порядок (зовнішній → внутрішній), як їх реєструє api.py:
    request_context   — X-Request-ID, X-Process-Time, рядок журналу;
    SecurityHeadersMiddleware — заголовки безпеки на кожній відповіді (чистий ASGI);
    rate_limit        — POST /api/scrape* і аналіз LLM: не більше N запитів за вікно з однієї адреси → 429;
    invalidate_cache  — успішний запис у новини → нова версія кешу (після COMMIT).

Rate limit — `RateLimitRepository` + `RateLimitMiddleware` стартового шаблону бота.
Рефакторинг кроку 4:
- aiogram-middleware → HTTP-middleware FastAPI; ключ — адреса клієнта + дія, а не user_id Telegram;
- `INCR`, а потім окремий `EXPIRE` (якщо count == 1) → одна транзакція `INCR` + `EXPIRE … NX`:
  якщо процес упаде між двома командами, ключ без TTL заблокує клієнта назавжди;
- у старому docstring алгоритм названо «Sliding Window Counter», але це **фіксоване вікно**
  (лічильник обнуляється разом із ключем) — назву виправлено, різницю пояснено в книзі (крок 4).
Крок 7: аналіз LLM коштує грошей і квоти — свій ліміт (`ANALYZE_RATE_LIMIT`), ключ `rate:analyze:<адреса>`.
Крок 8: вхід адміна — `LOGIN_RATE_LIMIT` спроб за `LOGIN_RATE_WINDOW` с з однієї адреси: пароль не підбереш
перебором (bcrypt сповільнює кожну спробу, ліміт — їхню кількість); збір з RSS-джерела теж скидає кеш.
Виправлення безпеки (після рецензії):
- `LIMITS` — одна таблиця лімітів (з кроку 9 ліміт збору звідси бере й бот: той самий `/scrape`);
- `SecurityHeadersMiddleware` — браузер не вгадує тип (`nosniff`), не вбудовує відповіді у фрейм, не передає
  Referer; на JSON-відповідях — CSP `default-src 'none'`. Сторінки /docs і /redoc без CSP: Swagger UI
  вантажить скрипти з CDN. HSTS ставить той, хто знімає TLS (nginx чи Caddy), а не застосунок.
"""
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .cache import NewsCache, get_redis

logger = logging.getLogger("news_hub")

CallNext = Callable[[Request], Awaitable[Response]]

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "5"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))      # секунд
ANALYZE_RATE_LIMIT = int(os.getenv("ANALYZE_RATE_LIMIT", "10"))    # запитів до LLM за вікно
LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "5"))         # крок 8: спроб входу за вікно
LOGIN_RATE_WINDOW = int(os.getenv("LOGIN_RATE_WINDOW", "300"))     # секунд

# дія → (запитів, за скільки секунд); ключ лічильника — rate:<дія>:<клієнт>
LIMITS = {"scrape": (RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW), "analyze": (ANALYZE_RATE_LIMIT, RATE_LIMIT_WINDOW),
          "login": (LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW)}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",        # JSON — це JSON, а не «може, HTML»
    "X-Frame-Options": "DENY",                  # не вбудовувати в чужі сторінки (clickjacking)
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'"   # API віддає дані, а не сторінки: нічого не вантажити
DOCS_PATHS = ("/docs", "/redoc")


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


class SecurityHeadersMiddleware:
    """Чистий ASGI-middleware, а не `@app.middleware("http")`: лише дописує заголовки в початок відповіді.

    Кожен шар `app.middleware("http")` (BaseHTTPMiddleware) змінює, коли саме закінчуються фонові задачі
    відносно відповіді, — з ще одним таким шаром тести фонового аналізу почали іноді падати (3 з 20 прогонів). Цьому
    шару тіло запиту й відповіді не потрібне, тож він працює на рівні ASGI-повідомлень і нічого не змінює.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = str(scope["path"]).startswith(DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if not is_docs:
                    headers.setdefault("Content-Security-Policy", API_CSP)
            await send(message)

        await self.app(scope, receive, send_with_headers)


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
    """Яка «дорога» дія: scrape — завантаження сайту, analyze — виклик LLM, login — вхід; None — без ліміту."""
    path = request.url.path
    if request.method != "POST":
        return None
    if path == "/api/admin/token":
        return "login"
    if path.startswith("/api/scrape"):
        return "scrape"
    if path.endswith("/analyze") or path.startswith("/api/analyze"):
        return "analyze"
    return None


async def rate_limit(request: Request, call_next: CallNext) -> Response:
    action = limited_action(request)
    if action is None:
        return await call_next(request)
    limit, window = LIMITS[action]
    limiter = RateLimiter(get_redis(request), limit=limit, window=window)
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

    Чому тут, а не в ендпоінті: COMMIT робить get_db (крок 3) уже ПІСЛЯ ендпоінта. Інвалідація в
    ендпоінті йшла б до COMMIT, і паралельний GET встиг би закешувати старі дані під новою версією.
    Middleware отримує відповідь, коли COMMIT уже відбувся (scope="function").
    """
    response = await call_next(request)
    path = request.url.path
    if (request.method in WRITE_METHODS and response.status_code < 400
            and (path.startswith("/api/news") or path == "/api/scrape"
                 or (path.startswith("/api/sources/") and path.endswith("/fetch")))):
        await NewsCache(get_redis(request)).invalidate()
    return response
