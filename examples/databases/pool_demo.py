"""Пул з'єднань: черга і тайм-аут, pool_pre_ping після обриву, тайм-аут запиту, з'єднання на воркери,
сесія, що тримає з'єднання під час чужого await, asyncpg напряму проти SQLAlchemy. Лише PostgreSQL.

    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres python pool_demo.py
"""
import asyncio
import os
import sys
import time

import asyncpg
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.getenv("DATABASE_URL", "")
if not URL.startswith("postgresql"):
    sys.exit("pool_demo.py потребує PostgreSQL: DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres")
RAW_URL = URL.replace("postgresql+asyncpg", "postgresql")


def error(exc: BaseException) -> str:
    text_ = str(exc).splitlines()[0]
    if text_.startswith("("):
        text_ = text_.split(") ", 1)[-1]
    return f"{type(exc).__name__}: {text_[:110]}"


async def backends(engine: AsyncEngine, app: str) -> int:
    async with engine.connect() as conn:
        return await conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE application_name = :app"),
                                 {"app": app})


async def main() -> None:
    print("--- 0. скільки коштує з'єднання: нове чи з пулу (середнє з 50)")
    started = time.perf_counter()
    for _ in range(50):
        conn = await asyncpg.connect(RAW_URL)
        await conn.fetchval("SELECT 1")
        await conn.close()
    fresh = (time.perf_counter() - started) / 50
    pool = await asyncpg.create_pool(RAW_URL, min_size=1, max_size=1)
    started = time.perf_counter()
    for _ in range(50):
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    pooled = (time.perf_counter() - started) / 50
    await pool.close()
    print(f"    нове з'єднання + SELECT 1: {fresh * 1000:5.2f} мс | з пулу + SELECT 1: {pooled * 1000:5.2f} мс")

    print("--- 1. pool_size=2, max_overflow=1: 5 запитів по 0,5 с одночасно")
    engine = create_async_engine(URL, pool_size=2, max_overflow=1, pool_timeout=2)
    started = time.perf_counter()

    async def request(n: int, seconds: float) -> str:
        async with engine.connect() as conn:
            got = time.perf_counter() - started
            await conn.execute(text("SELECT pg_sleep(:s)"), {"s": seconds})
            return f"запит {n}: з'єднання через {got:4.2f} с"

    for line in await asyncio.gather(*(request(n, 0.5) for n in range(1, 6))):
        print("   ", line)
    print("    стан пулу:", engine.pool.status())

    print("--- 2. те саме, але запити по 3 с, pool_timeout=2")
    started = time.perf_counter()
    for result in await asyncio.gather(*(request(n, 3) for n in range(1, 6)), return_exceptions=True):
        print("   ", result if isinstance(result, str) else error(result))
    await engine.dispose()

    print("--- 3. PostgreSQL обірвав з'єднання (перезапуск, тайм-аут простою)")
    for pre_ping in (False, True):
        engine = create_async_engine(URL, pool_size=1, max_overflow=0, pool_pre_ping=pre_ping)
        async with engine.connect() as conn:
            pid = await conn.scalar(text("SELECT pg_backend_pid()"))
        killer = await asyncpg.connect(RAW_URL)
        await killer.execute("SELECT pg_terminate_backend($1)", pid)
        await killer.close()
        for attempt in (1, 2):
            try:
                async with engine.connect() as conn:
                    new_pid = await conn.scalar(text("SELECT pg_backend_pid()"))
                print(f"    pool_pre_ping={pre_ping!s:5} запит {attempt}: ok, нове з'єднання {new_pid != pid}")
            except DBAPIError as exc:
                print(f"    pool_pre_ping={pre_ping!s:5} запит {attempt}: {error(exc)}")
        await engine.dispose()

    print("--- 4. тайм-аут запиту: statement_timeout у PostgreSQL")
    engine = create_async_engine(URL, connect_args={"server_settings": {"statement_timeout": "500"}})
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT pg_sleep(2)"))
    except DBAPIError as exc:
        print("   ", error(exc))
    await engine.dispose()

    print("--- 5. з'єднань на сервері: 3 процеси-«воркери» × (pool_size=4 + max_overflow=2)")
    workers = [create_async_engine(URL, pool_size=4, max_overflow=2,
                                   connect_args={"server_settings": {"application_name": "part05-worker"}})
               for _ in range(3)]

    async def hold(engine: AsyncEngine) -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT pg_sleep(0.5)"))

    observer = create_async_engine(URL, poolclass=NullPool)            # окреме з'єднання для підрахунку

    async def peak() -> int:
        await asyncio.sleep(0.25)
        return await backends(observer, "part05-worker")

    *_, seen = await asyncio.gather(*(hold(w) for w in workers for _ in range(6)), peak())
    print(f"    з'єднань під навантаженням: {seen} (3 × 6 = 18)")
    async with observer.connect() as conn:
        limit = await conn.scalar(text("SHOW max_connections"))
    print("    max_connections сервера:", limit)
    print("    після навантаження в пулах лишилось:", [w.pool.checkedin() for w in workers], "(pool_size, не 6)")
    print("    після dispose() усіх пулів:", [w.pool.checkedin() for w in workers if not await w.dispose()],
          "| на сервері:", await backends(observer, "part05-worker"))
    await observer.dispose()

    print("--- 6. сесія тримає з'єднання, поки ендпоінт чекає чужий API")
    engine = create_async_engine(URL, pool_size=2, max_overflow=0, pool_timeout=1)

    async def endpoint(n: int, release_first: bool) -> str:
        async with AsyncSession(engine) as session:
            title = await session.scalar(select(text("'новина'")))
            if release_first:
                await session.commit()                      # з'єднання повертається в пул до довгого await
            await asyncio.sleep(1.5)                        # виклик LLM, HTTP-запит до іншого сервісу
            return f"{n}:{title}"

    for release_first in (False, True):
        results = await asyncio.gather(*(endpoint(n, release_first) for n in range(4)), return_exceptions=True)
        ok = sum(isinstance(r, str) for r in results)
        failed = {error(r)[:80] for r in results if not isinstance(r, str)}
        print(f"    commit до await={release_first!s:5} ok: {ok}/4", *failed)
    await engine.dispose()

    print("--- 7. asyncpg напряму і SQLAlchemy: 2000 запитів по одному рядку")
    pool = await asyncpg.create_pool(RAW_URL, min_size=2, max_size=10, command_timeout=30)
    engine = create_async_engine(URL, pool_size=10)

    async def raw(i: int) -> str:
        async with pool.acquire() as conn:
            return await conn.fetchval("SELECT $1::text", str(i))

    async def core(i: int) -> str:
        async with engine.connect() as conn:
            return await conn.scalar(text("SELECT CAST(:v AS text)"), {"v": str(i)})

    for title, job in (("asyncpg pool", raw), ("SQLAlchemy Core", core)):
        await asyncio.gather(*(job(i) for i in range(50)))                 # прогрів
        started = time.perf_counter()
        results = await asyncio.gather(*(job(i) for i in range(2000)))
        print(f"    {title:16} {time.perf_counter() - started:5.2f} с, останній результат {results[-1]!r}")
    await pool.close()
    await engine.dispose()

    print("--- 8. транзакція asyncpg: rollback() після commit()")
    conn = await asyncpg.connect(RAW_URL)
    tx = conn.transaction()
    await tx.start()
    await tx.commit()
    try:
        await tx.rollback()
    except asyncpg.InterfaceError as exc:
        print("   ", error(exc))
    async with conn.transaction():                          # контекстний менеджер: COMMIT або ROLLBACK сам
        await conn.execute("SELECT 1")
    print("    async with conn.transaction(): ok")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
