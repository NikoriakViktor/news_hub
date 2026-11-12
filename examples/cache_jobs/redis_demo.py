"""Redis для API: рядки й TTL, структури даних, атомарність, pipeline і транзакції, WATCH, Lua, SCAN, fakeredis.

    python redis_demo.py                                    # fakeredis: Redis у пам'яті процесу
    REDIS_URL=redis://localhost:6390/0 python redis_demo.py  # справжній Redis (див. README)

Демо працює в базі 0 і на початку видаляє лише свої ключі з префіксом `demo:`.
"""
import asyncio
import os
import time

import fakeredis
from redis.asyncio import Redis
from redis.exceptions import ResponseError, WatchError

REDIS_URL = os.getenv("REDIS_URL", "fakeredis://")
BACKEND = "fakeredis" if REDIS_URL.startswith("fakeredis") else "Redis " + REDIS_URL


def make_redis(decode: bool = True) -> Redis:
    if REDIS_URL.startswith("fakeredis"):
        return fakeredis.FakeAsyncRedis(server=SERVER, decode_responses=decode)
    return Redis.from_url(REDIS_URL, decode_responses=decode)


SERVER = fakeredis.FakeServer()       # один «сервер» для всіх клієнтів цього демо


def section(title: str) -> None:
    print(f"--- {title}")


async def cleanup(r: Redis) -> None:
    keys = [key async for key in r.scan_iter("demo:*")]
    if keys:
        await r.delete(*keys)


async def strings_and_ttl(r: Redis) -> None:
    section("1. рядки, числа, decode_responses")
    raw = make_redis(decode=False)
    await r.set("demo:courier:1:name", "Оксана")
    print("decode_responses=True :", repr(await r.get("demo:courier:1:name")))
    print("decode_responses=False:", repr(await raw.get("demo:courier:1:name")))
    await raw.aclose()
    print("немає ключа:", await r.get("demo:courier:99:name"),
          "| EXISTS двох ключів:", await r.exists("demo:courier:1:name", "demo:courier:99:name"))
    await r.set("demo:counter", 7)
    print("число повертається рядком:", repr(await r.get("demo:counter")), "| INCR:", await r.incr("demo:counter"))

    section("2. TTL: -1, -2, і SET, що стирає TTL")
    await r.set("demo:report", "...", ex=300)
    print("SET … EX 300 → TTL", await r.ttl("demo:report"))
    print("ключ без TTL → TTL", await r.ttl("demo:courier:1:name"), "| немає ключа → TTL", await r.ttl("demo:nope"))
    await r.set("demo:report", "новий звіт")
    print("SET без EX поверх ключа з TTL → TTL", await r.ttl("demo:report"), "(ключ став вічним)")
    await r.set("demo:report", "...", ex=300)
    await r.set("demo:report", "ще новіший", keepttl=True)
    print("SET … KEEPTTL → TTL", await r.ttl("demo:report"))
    print("EXPIRE NX на ключ з TTL:", await r.expire("demo:report", 10, nx=True), "→ TTL", await r.ttl("demo:report"))
    await r.incr("demo:hits")
    print("INCR не ставить TTL → TTL", await r.ttl("demo:hits"))


async def structures(r: Redis) -> None:
    section("3. структури даних")
    await r.rpush("demo:queue", "задача 1", "задача 2", "задача 3")
    print("list  RPUSH×3, LPOP →", await r.lpop("demo:queue"), "| LLEN", await r.llen("demo:queue"))
    await r.hset("demo:job:42", mapping={"status": "running", "news_found": 0})
    await r.hincrby("demo:job:42", "news_found", 168)
    print("hash  HGETALL →", await r.hgetall("demo:job:42"))
    print("set   SADD Анна Богдан Анна →", await r.sadd("demo:visitors", "Анна", "Богдан", "Анна"),
          "нових | SCARD", await r.scard("demo:visitors"))
    await r.zadd("demo:rating", {"Оксана": 2130, "Тарас": 1570, "Ігор": 1040})
    await r.zincrby("demo:rating", 900, "Ігор")
    print("zset  ZREVRANGE 0 1 →", await r.zrevrange("demo:rating", 0, 1, withscores=True),
          "| ZREVRANK Ігор:", await r.zrevrank("demo:rating", "Ігор"))
    try:
        await r.lpush("demo:job:42", "x")
    except ResponseError as error:
        print("команда не того типу:", str(error)[:60])


async def atomicity() -> None:
    section(f"4. гонитва: GET + SET проти INCR, 4 клієнти × 500 ({BACKEND})")
    clients = [make_redis() for _ in range(4)]
    await clients[0].delete("demo:buggy", "demo:atomic")

    async def buggy(c: Redis) -> None:
        for _ in range(500):
            current = int(await c.get("demo:buggy") or 0)
            await c.set("demo:buggy", current + 1)

    async def atomic(c: Redis) -> None:
        for _ in range(500):
            await c.incr("demo:atomic")

    await asyncio.gather(*(buggy(c) for c in clients))
    await asyncio.gather(*(atomic(c) for c in clients))
    print("очікували 2000 | GET+SET:", await clients[0].get("demo:buggy"), "| INCR:", await clients[0].get("demo:atomic"))
    for c in clients:
        await c.aclose()


async def pipelines(r: Redis) -> None:
    section(f"5. pipeline: 1000 команд ({BACKEND})")
    start = time.perf_counter()
    for _ in range(1000):
        await r.incr("demo:p")
    one_by_one = time.perf_counter() - start
    start = time.perf_counter()
    async with r.pipeline(transaction=False) as pipe:
        for _ in range(1000):
            pipe.incr("demo:p")
        results = await pipe.execute()
    batched = time.perf_counter() - start
    print(f"по одній: {one_by_one * 1000:.0f} ms | pipeline: {batched * 1000:.0f} ms | останнє значення {results[-1]}")

    section("6. MULTI/EXEC — разом, але без відкату")
    await r.set("demo:balance", 100)
    async with r.pipeline(transaction=True) as pipe:
        pipe.incrby("demo:balance", -30)
        pipe.lpush("demo:job:42", "x")             # помилка типу всередині транзакції
        pipe.incr("demo:ops")
        results = await pipe.execute(raise_on_error=False)
    print("результати:", [type(x).__name__ if isinstance(x, Exception) else x for x in results])
    print("після EXEC: balance =", await r.get("demo:balance"), "| ops =", await r.get("demo:ops"),
          "— решта команд виконалась")


async def check_and_set(r: Redis) -> None:
    section(f"7. «зняти, якщо вистачає»: наївно, WATCH, Lua — 10 одночасних зняттів по 30 з балансу 100 ({BACKEND})")
    clients = [make_redis() for _ in range(10)]

    async def naive(c: Redis) -> bool:
        balance = int(await c.get("demo:balance") or 0)
        await asyncio.sleep(0)                          # будь-який await — шанс для іншого клієнта
        if balance >= 30:
            await c.decrby("demo:balance", 30)
            return True
        return False

    async def watched(c: Redis) -> bool:
        async with c.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch("demo:balance")     # EXEC не виконається, якщо ключ змінили після WATCH
                    balance = int(await pipe.get("demo:balance") or 0)
                    if balance < 30:
                        await pipe.unwatch()
                        return False
                    pipe.multi()
                    pipe.decrby("demo:balance", 30)
                    await pipe.execute()
                    return True
                except WatchError:
                    watch_retries.append(1)              # хтось встиг раніше — спробувати знову
                    continue

    script = r.register_script("""
        local balance = tonumber(redis.call('GET', KEYS[1]) or '0')
        if balance < tonumber(ARGV[1]) then return 0 end
        redis.call('DECRBY', KEYS[1], ARGV[1])
        return 1
    """)

    async def lua(c: Redis) -> bool:
        return bool(await script(keys=["demo:balance"], args=[30], client=c))

    for name, action in (("наївно", naive), ("WATCH", watched), ("Lua", lua)):
        watch_retries: list[int] = []
        await r.set("demo:balance", 100)
        results = await asyncio.gather(*(action(c) for c in clients))
        extra = f" | повторів після WatchError: {len(watch_retries)}" if name == "WATCH" else ""
        print(f"{name:7} успішних зняттів: {sum(results)} | баланс: {await r.get('demo:balance')}{extra}")
    for c in clients:
        await c.aclose()


async def scan_not_keys(r: Redis) -> None:
    section("8. SCAN замість KEYS")
    async with r.pipeline(transaction=False) as pipe:
        for number in range(1000):
            pipe.set(f"demo:cache:{number}", "x", ex=60)
        await pipe.execute()
    found = [key async for key in r.scan_iter("demo:cache:*", count=200)]
    print("SCAN знайшов", len(found), "ключів кількома викликами, не блокуючи сервер на весь прохід")


async def fake_servers() -> None:
    section("9. fakeredis: окремий сервер на кожен клієнт, якщо не передати спільний")
    a, b = fakeredis.FakeAsyncRedis(decode_responses=True), fakeredis.FakeAsyncRedis(decode_responses=True)
    await a.set("demo:shared", "з клієнта a")
    print("два FakeAsyncRedis() без параметрів — b бачить:", await b.get("demo:shared"))
    server = fakeredis.FakeServer()
    c = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    d = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    await c.set("demo:shared", "з клієнта c")
    print("зі спільним FakeServer — d бачить:", await d.get("demo:shared"))
    for client in (a, b, c, d):
        await client.aclose()


async def pubsub(r: Redis) -> None:
    section("10. Pub/Sub: хто не слухав — не отримав")
    await r.publish("demo:events", "до підписки")
    listener = r.pubsub()
    await listener.subscribe("demo:events")
    await listener.get_message(timeout=1)                # підтвердження підписки
    receivers = await r.publish("demo:events", "нова новина #104")
    message = await listener.get_message(timeout=1)
    print("PUBLISH повернув підписників:", receivers, "| отримано:", message["data"] if message else None)
    await listener.aclose()


async def server_config(r: Redis) -> None:
    if REDIS_URL.startswith("fakeredis"):
        return
    section("11. налаштування сервера")
    config = await r.config_get("maxmemory*")
    print("maxmemory:", config.get("maxmemory"), "| maxmemory-policy:", config.get("maxmemory-policy"))
    print("appendonly:", (await r.config_get("appendonly")).get("appendonly"),
          "| save:", (await r.config_get("save")).get("save"))


async def main() -> None:
    r = make_redis()
    await cleanup(r)
    await strings_and_ttl(r)
    await structures(r)
    await atomicity()
    await pipelines(r)
    await check_and_set(r)
    await scan_not_keys(r)
    await fake_servers()
    await pubsub(r)
    await server_config(r)
    await cleanup(r)
    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
