"""Rate limit: чотири алгоритми на одному трафіку, атомарність у Redis, 429 + Retry-After, ключ клієнта за проксі.

    python rate_limit_demo.py                                    # fakeredis
    REDIS_URL=redis://localhost:6390/0 python rate_limit_demo.py  # справжній Redis: тут видно гонитву

Частина 1 — алгоритми з «ручним» годинником (без Redis): результат однаковий щоразу.
"""
import asyncio
import os
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable

import fakeredis
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

REDIS_URL = os.getenv("REDIS_URL", "fakeredis://")
BACKEND = "fakeredis" if REDIS_URL.startswith("fakeredis") else "Redis " + REDIS_URL
SERVER = fakeredis.FakeServer()


def make_redis() -> Redis:
    if REDIS_URL.startswith("fakeredis"):
        return fakeredis.FakeAsyncRedis(server=SERVER, decode_responses=True)
    return Redis.from_url(REDIS_URL, decode_responses=True)


def section(title: str) -> None:
    print(f"--- {title}")


# Частина 1. Алгоритми в пам'яті, час — аргумент -------------------------------------------------------

class FixedWindow:
    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window, self.counts = limit, window, {}

    def hit(self, now: float) -> bool:
        bucket = int(now // self.window)               # номер вікна: 0–59.99 с → 0, 60–119.99 → 1
        self.counts[bucket] = self.counts.get(bucket, 0) + 1
        return self.counts[bucket] <= self.limit


class SlidingLog:
    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window, self.log = limit, window, deque()

    def hit(self, now: float) -> bool:
        while self.log and self.log[0] <= now - self.window:
            self.log.popleft()                          # забути запити, старші за вікно
        if len(self.log) < self.limit:
            self.log.append(now)
            return True
        return False


class SlidingWindowCounter:
    """Два лічильники фіксованих вікон; попереднє враховується пропорційно до того, скільки його ще «у вікні»."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window, self.counts = limit, window, {}

    def hit(self, now: float) -> bool:
        bucket = int(now // self.window)
        elapsed = (now % self.window) / self.window
        estimate = self.counts.get(bucket - 1, 0) * (1 - elapsed) + self.counts.get(bucket, 0)
        if estimate < self.limit:
            self.counts[bucket] = self.counts.get(bucket, 0) + 1
            return True
        return False


class TokenBucket:
    """Відро на `capacity` жетонів, поповнюється rate жетонів за секунду; запит забирає жетон."""

    def __init__(self, capacity: int, per_seconds: float) -> None:
        self.capacity, self.rate = capacity, capacity / per_seconds
        self.tokens, self.updated = float(capacity), 0.0

    def hit(self, now: float) -> bool:
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


ALGORITHMS = {"фіксоване вікно": FixedWindow, "ковзний журнал": SlidingLog,
              "ковзний лічильник": SlidingWindowCounter, "token bucket": TokenBucket}


def max_in_any_window(times: list[float], window: float) -> int:
    best, start = 0, 0
    for end in range(len(times)):
        while times[end] - times[start] >= window:
            start += 1
        best = max(best, end - start + 1)
    return best


def algorithms() -> None:
    limit, window = 10, 60.0
    scenarios = {
        "межа вікон: 10 о 59 с, 10 о 61 с": [59.0] * 10 + [61.0] * 10,
        "рівномірно: 1 запит / 4 с, 2 хв": [float(t) for t in range(0, 120, 4)],
        "сплеск: 25 запитів о 0 с": [0.0] * 25,
        "сплеск, тиша 30 с, сплеск": [0.0] * 10 + [30.0] * 10,
    }
    section(f"1. чотири алгоритми, ліміт {limit} за {window:.0f} с: пройшло (макс. за будь-які 60 с)")
    print(f"{'сценарій':34}" + "".join(f"{name:>20}" for name in ALGORITHMS))
    for title, times in scenarios.items():
        row = f"{title:34}"
        for cls in ALGORITHMS.values():
            limiter = cls(limit, window)
            passed = [t for t in times if limiter.hit(t)]
            cell = f"{len(passed)} ({max_in_any_window(passed, window)})"
            row += f"{cell:>20}"
        print(row)


# Частина 2. Те саме в Redis: атомарність --------------------------------------------------------------

async def fixed_window_redis(r: Redis, key: str, limit: int, window: int) -> tuple[bool, int]:
    async with r.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window, nx=True)
        pipe.ttl(key)
        count, _, ttl = await pipe.execute()
    return count <= limit, max(ttl, 0)


async def sliding_log_naive(r: Redis, key: str, limit: int, window: int) -> tuple[bool, int]:
    now_ms = int(time.time() * 1000)
    await r.zremrangebyscore(key, 0, now_ms - window * 1000)
    count = await r.zcard(key)                          # перевірка…
    if count >= limit:
        return False, window
    await r.zadd(key, {uuid.uuid4().hex: now_ms})       # …і запис — дві окремі команди
    await r.pexpire(key, window * 1000)
    return True, 0


SLIDING_LOG_LUA = """
local key, now, window, limit, member = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
if redis.call('ZCARD', key) >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, math.ceil((tonumber(oldest[2]) + window - now) / 1000)}
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
return {1, 0}
"""

TOKEN_BUCKET_LUA = """
local key, now, capacity, rate = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
local state = redis.call('HMGET', key, 'tokens', 'updated')
local tokens = tonumber(state[1]) or capacity
local updated = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + (now - updated) / 1000 * rate)
local allowed, retry = 0, 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry = math.ceil((1 - tokens) / rate)
end
redis.call('HSET', key, 'tokens', tostring(tokens), 'updated', now)
redis.call('PEXPIRE', key, math.ceil(capacity / rate * 1000))
return {allowed, retry}
"""


async def atomic_in_redis() -> None:
    section(f"2. 50 одночасних запитів, ліміт 10 ({BACKEND})")
    r = make_redis()
    clients = [make_redis() for _ in range(50)]
    sliding = r.register_script(SLIDING_LOG_LUA)
    bucket = r.register_script(TOKEN_BUCKET_LUA)

    async def run_sliding_lua(c: Redis, key: str) -> tuple[bool, int]:
        allowed, retry = await sliding(keys=[key], args=[int(time.time() * 1000), 60_000, 10, uuid.uuid4().hex],
                                       client=c)
        return bool(allowed), int(retry)

    async def run_bucket(c: Redis, key: str) -> tuple[bool, int]:
        allowed, retry = await bucket(keys=[key], args=[int(time.time() * 1000), 10, 10 / 60], client=c)
        return bool(allowed), int(retry)

    cases: dict[str, Callable[[Redis, str], Awaitable[tuple[bool, int]]]] = {
        "фіксоване вікно, MULTI": lambda c, k: fixed_window_redis(c, k, 10, 60),
        "ковзний журнал, наївно": lambda c, k: sliding_log_naive(c, k, 10, 60),
        "ковзний журнал, Lua": run_sliding_lua,
        "token bucket, Lua": run_bucket,
    }
    for name, hit in cases.items():
        key = f"demo:rate:{uuid.uuid4().hex[:6]}"
        results = await asyncio.gather(*(hit(c, key) for c in clients))
        allowed = sum(ok for ok, _ in results)
        retry = sorted({retry for ok, retry in results if not ok})
        print(f"{name:24} пройшло: {allowed:2} | Retry-After у відмовах: {retry[:3]}")
        await r.delete(key)
    for c in [r, *clients]:
        await c.aclose()


# Частина 3. HTTP: 429, Retry-After, ключ клієнта за проксі --------------------------------------------

def make_app(redis: Redis, key_from: str) -> FastAPI:
    app = FastAPI()

    @app.post("/api/scrape")
    async def scrape() -> dict[str, bool]:
        return {"started": True}

    @app.middleware("http")
    async def limit(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if key_from == "x-forwarded-for":                       # НЕПРАВИЛЬНО: вірити заголовку від будь-кого
            client = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or "unknown"
        else:
            client = request.client.host if request.client else "unknown"
        allowed, ttl = await fixed_window_redis(redis, f"demo:rate:http:{key_from}:{client}", 3, 60)
        if not allowed:
            return JSONResponse({"detail": "забагато запитів"}, status_code=429, headers={"Retry-After": str(ttl)})
        return await call_next(request)

    return app


async def http_part() -> None:
    redis = make_redis()
    keys = [key async for key in redis.scan_iter("demo:rate:http:*")]
    if keys:
        await redis.delete(*keys)

    section("3. 429 і Retry-After: 5 запитів з однієї адреси, ліміт 3 за 60 с")
    app = make_app(redis, "client")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=("203.0.113.5", 5000)),
                                 base_url="http://api") as client:
        for _ in range(5):
            response = await client.post("/api/scrape")
            print(response.status_code, "Retry-After:", response.headers.get("retry-after"))

    section("4. за проксі: усі клієнти мають адресу nginx")
    nginx = ("172.28.0.10", 40000)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(make_app(redis, "client-behind-proxy"),
                                                               client=nginx), base_url="http://api") as client:
        statuses = [(await client.post("/api/scrape", headers={"X-Forwarded-For": f"198.51.100.{n}"})).status_code
                    for n in range(1, 6)]
    print("5 різних людей через nginx, ключ = request.client.host:", statuses)

    section("5. X-Forwarded-For без перевірки: атакувальник міняє «адресу» щоразу")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(make_app(redis, "x-forwarded-for"),
                                                               client=("203.0.113.66", 1)), base_url="http://api") as client:
        statuses = [(await client.post("/api/scrape", headers={"X-Forwarded-For": f"10.0.0.{n}"})).status_code
                    for n in range(10)]
    print("10 запитів напряму, кожен з новим X-Forwarded-For:", statuses)

    section("6. ProxyHeadersMiddleware з довіреною адресою проксі")

    def trusted_app(key_from: str) -> ProxyHeadersMiddleware:
        return ProxyHeadersMiddleware(make_app(redis, key_from), trusted_hosts="172.28.0.10")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(trusted_app("trusted-1"), client=nginx),
                                 base_url="http://api") as client:
        statuses = [(await client.post("/api/scrape", headers={"X-Forwarded-For": f"198.51.100.{n}"})).status_code
                    for n in range(1, 6)]
    print("5 різних людей через довірений nginx:", statuses)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(trusted_app("trusted-2"),
                                                               client=("203.0.113.66", 1)), base_url="http://api") as client:
        statuses = [(await client.post("/api/scrape", headers={"X-Forwarded-For": f"10.0.0.{n}"})).status_code
                    for n in range(5)]
    print("атакувальник напряму з підробленим X-Forwarded-For:", statuses)

    keys = [key async for key in redis.scan_iter("demo:rate:*")]
    if keys:
        await redis.delete(*keys)
    await redis.aclose()


if __name__ == "__main__":
    algorithms()
    asyncio.run(atomic_in_redis())
    asyncio.run(http_part())
