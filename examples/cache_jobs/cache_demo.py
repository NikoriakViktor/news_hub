"""Стратегії кешу: cache-aside, застарілі дані, інвалідація (DEL, версія, теги), гонитва з записом,
write-through, cache stampede, розкид TTL, кеш недоступний.

    python cache_demo.py                                    # fakeredis
    REDIS_URL=redis://localhost:6390/0 python cache_demo.py  # справжній Redis

«База» тут — словник із затримкою й лічильником звернень: так видно, скільки разів кеш її пощадив.
"""
import asyncio
import json
import os
import random
import time

import fakeredis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

REDIS_URL = os.getenv("REDIS_URL", "fakeredis://")
SERVER = fakeredis.FakeServer()


def make_redis() -> Redis:
    if REDIS_URL.startswith("fakeredis"):
        return fakeredis.FakeAsyncRedis(server=SERVER, decode_responses=True)
    return Redis.from_url(REDIS_URL, decode_responses=True)


def section(title: str) -> None:
    print(f"--- {title}")


class SlowDB:
    """Джерело правди: читання займає `delay` секунд, кожне звернення рахується."""

    def __init__(self, delay: float = 0.2) -> None:
        self.rows = {"news:1": {"id": 1, "title": "Стара назва"}}
        self.delay, self.reads = delay, 0

    async def read(self, key: str) -> dict[str, object]:
        self.reads += 1
        snapshot = dict(self.rows[key])               # що було в базі на початку читання
        await asyncio.sleep(self.delay)
        return snapshot

    async def write(self, key: str, **fields: object) -> None:
        self.rows[key] = {**self.rows[key], **fields}


async def cache_aside(r: Redis, db: SlowDB, key: str, ttl: int = 60) -> dict[str, object]:
    cached = await r.get(f"demo:cache:{key}")
    if cached is not None:                            # hit
        return json.loads(cached)
    value = await db.read(key)                        # miss
    await r.set(f"demo:cache:{key}", json.dumps(value, ensure_ascii=False), ex=ttl)
    return value


async def demo_cache_aside(r: Redis) -> None:
    section("1. cache-aside: miss, потім hit")
    db = SlowDB()
    for attempt in range(1, 4):
        start = time.perf_counter()
        value = await cache_aside(r, db, "news:1")
        print(f"{attempt}: {value['title']} за {(time.perf_counter() - start) * 1000:.0f} ms")
    print("звернень до бази:", db.reads, "| TTL:", await r.ttl("demo:cache:news:1"))

    section("2. запис у базу без інвалідації — кеш бреше до кінця TTL")
    await db.write("news:1", title="Нова назва")
    print("у базі:", db.rows["news:1"]["title"], "| з кешу:", (await cache_aside(r, db, "news:1"))["title"])


async def demo_invalidation(r: Redis) -> None:
    section("3. інвалідація стрічки з багатьма комбінаціями параметрів")
    params = [{"page": page, "category": category} for page in (1, 2, 3) for category in ("all", "sport", "it")]

    # а) DEL: треба знати всі ключі — інакше частина лишається
    for p in params:
        await r.set(f"demo:list:{p['page']}:{p['category']}", "[...]", ex=60)
    await r.delete("demo:list:1:all")                 # «очевидний» ключ
    left = [key async for key in r.scan_iter("demo:list:*")]
    print(f"DEL demo:list:1:all — лишилось застарілих ключів: {len(left)} з {len(params)}")

    # б) версія: ключі містять номер версії; INCR — і старі просто не читаються
    async def versioned_key(p: dict[str, object]) -> str:
        version = await r.get("demo:news:version") or "0"
        return f"demo:news:v{version}:list:{p['page']}:{p['category']}"

    for p in params:
        await r.set(await versioned_key(p), "[...]", ex=60)
    await r.incr("demo:news:version")
    hits = sum([await r.exists(await versioned_key(p)) for p in params])
    old = len([key async for key in r.scan_iter("demo:news:v0:*")])
    print(f"INCR версії — влучань у кеш після запису: {hits}; старих ключів у пам'яті до кінця TTL: {old}")

    # в) теги: множина ключів на тег; інвалідація — SMEMBERS + DEL, одна транзакція
    for p in params:
        key = f"demo:tagged:{p['page']}:{p['category']}"
        async with r.pipeline(transaction=True) as pipe:
            pipe.set(key, "[...]", ex=60)
            pipe.sadd(f"demo:tag:{p['category']}", key)
            pipe.expire(f"demo:tag:{p['category']}", 60)
            await pipe.execute()
    keys = await r.smembers("demo:tag:sport")
    async with r.pipeline(transaction=True) as pipe:
        pipe.delete(*keys)
        pipe.delete("demo:tag:sport")
        await pipe.execute()
    left = sorted([key async for key in r.scan_iter("demo:tagged:*")])
    print(f"тег sport скинуто: видалено {len(keys)} ключі, лишились {len(left)} — інші категорії не зачеплено")


async def demo_race(r: Redis) -> None:
    section("4. гонитва читання й запису: DEL проти версії")
    # читач: miss → повільне читання бази; поки читає, письменник змінює базу й скидає кеш

    async def run(strategy: str) -> str:
        db = SlowDB(delay=0.2)
        await r.delete("demo:cache:news:1", "demo:v:version")

        async def key() -> str:
            if strategy == "DEL":
                return "demo:cache:news:1"
            return f"demo:v{await r.get('demo:v:version') or '0'}:news:1"

        async def reader() -> None:
            k = await key()                           # ключ (і версію) визначено ДО читання бази
            if await r.get(k) is None:
                value = await db.read("news:1")       # читає «Стара назва»
                await r.set(k, json.dumps(value, ensure_ascii=False), ex=60)

        async def writer() -> None:
            await asyncio.sleep(0.05)                 # читач уже в базі
            await db.write("news:1", title="Нова назва")
            if strategy == "DEL":
                await r.delete("demo:cache:news:1")   # кешу ще немає — видаляти нічого
            else:
                await r.incr("demo:v:version")

        await asyncio.gather(reader(), writer())
        cached = await r.get(await key())
        return json.loads(cached)["title"] if cached else "(порожньо — наступний читач піде в базу)"

    for strategy in ("DEL", "версія"):
        print(f"{strategy:7} у базі: Нова назва | у кеші для наступних читачів: {await run(strategy)}")


async def demo_write_through(r: Redis) -> None:
    section("5. write-through: запис оновлює і базу, і кеш")
    db = SlowDB()
    await r.delete("demo:cache:news:1")
    await cache_aside(r, db, "news:1")

    async def update_title(title: str) -> None:
        await db.write("news:1", title=title)          # спершу джерело правди
        value = await db.read("news:1")
        await r.set("demo:cache:news:1", json.dumps(value, ensure_ascii=False), ex=60)

    start = time.perf_counter()
    await update_title("Назва після редагування")
    write_ms = (time.perf_counter() - start) * 1000
    reads_before = db.reads
    value = await cache_aside(r, db, "news:1")
    print(f"запис зайняв {write_ms:.0f} ms (база + кеш) | читання після запису: {value['title']}"
          f" | звернень до бази при читанні: {db.reads - reads_before}")


async def demo_stampede(r: Redis) -> None:
    section("6. cache stampede: 50 одночасних запитів на холодний ключ")

    async def plain(db: SlowDB) -> None:
        await cache_aside(r, db, "news:1")

    locks: dict[str, asyncio.Future[dict[str, object]]] = {}

    async def single_flight(db: SlowDB) -> None:
        """В одному процесі: перший запит рахує, решта чекають на той самий Future."""
        cached = await r.get("demo:cache:news:1")
        if cached is not None:
            return
        if "news:1" in locks:
            await locks["news:1"]
            return
        future: asyncio.Future[dict[str, object]] = asyncio.get_running_loop().create_future()
        locks["news:1"] = future
        try:
            value = await db.read("news:1")
            await r.set("demo:cache:news:1", json.dumps(value, ensure_ascii=False), ex=60)
            future.set_result(value)
        finally:
            del locks["news:1"]

    async def redis_lock(db: SlowDB) -> None:
        """Між процесами: SET NX EX — лише один перераховує; інші чекають і читають кеш."""
        for _ in range(100):
            cached = await r.get("demo:cache:news:1")
            if cached is not None:
                return
            if await r.set("demo:lock:news:1", "1", nx=True, ex=5):   # 5 с — якщо власник упаде
                try:
                    value = await db.read("news:1")
                    await r.set("demo:cache:news:1", json.dumps(value, ensure_ascii=False), ex=60)
                finally:
                    await r.delete("demo:lock:news:1")
                return
            await asyncio.sleep(0.02)
        await db.read("news:1")                       # не дочекались — краще повільно, ніж ніяк

    for name, handler in (("без захисту", plain), ("single-flight", single_flight), ("Redis-замок", redis_lock)):
        db = SlowDB(delay=0.2)
        await r.delete("demo:cache:news:1", "demo:lock:news:1")
        start = time.perf_counter()
        await asyncio.gather(*(handler(db) for _ in range(50)))
        print(f"{name:14} звернень до бази: {db.reads:2} | усі 50 відповіли за {(time.perf_counter() - start) * 1000:.0f} ms")


async def demo_jitter(r: Redis) -> None:
    section("7. розкид TTL: ключі, створені разом, не мають зникати разом")
    random.seed(7)
    async with r.pipeline(transaction=False) as pipe:
        for number in range(100):
            pipe.set(f"demo:same:{number}", "x", ex=60)
            pipe.set(f"demo:jitter:{number}", "x", ex=60 + random.randint(0, 12))
        await pipe.execute()
    same = {await r.ttl(f"demo:same:{number}") for number in range(100)}
    jitter = [await r.ttl(f"demo:jitter:{number}") for number in range(100)]
    print(f"TTL 60 для всіх: різних моментів зникнення {len(same)} | 60 + randint(0, 12): {len(set(jitter))}"
          f" (від {min(jitter)} до {max(jitter)} с)")


async def demo_redis_down() -> None:
    section("8. Redis недоступний: кеш — прискорення, а не умова роботи")
    down = Redis.from_url("redis://127.0.0.1:6399/0", decode_responses=True, socket_connect_timeout=0.5)
    db = SlowDB(delay=0.01)
    try:
        await cache_aside(down, db, "news:1")
    except RedisConnectionError as error:
        print("cache-aside без обробки →", type(error).__name__, "— запит упаде з 500")

    async def safe_cache_aside(key: str) -> dict[str, object]:
        try:
            cached = await down.get(f"demo:cache:{key}")
        except RedisError:
            cached = None                             # кеш недоступний — це просто miss
        if cached is not None:
            return json.loads(cached)
        value = await db.read(key)
        try:
            await down.set(f"demo:cache:{key}", json.dumps(value, ensure_ascii=False), ex=60)
        except RedisError:
            pass
        return value

    value = await safe_cache_aside("news:1")
    print("з try/except RedisError →", value["title"], "з бази")
    await down.aclose()


async def main() -> None:
    r = make_redis()
    keys = [key async for key in r.scan_iter("demo:*")]
    if keys:
        await r.delete(*keys)
    await demo_cache_aside(r)
    await demo_invalidation(r)
    await demo_race(r)
    await demo_write_through(r)
    await demo_stampede(r)
    await demo_jitter(r)
    await demo_redis_down()
    keys = [key async for key in r.scan_iter("demo:*")]
    if keys:
        await r.delete(*keys)
    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
