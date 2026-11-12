"""Паралельний збір сторінок: gather, return_exceptions, TaskGroup, Semaphore, тайм-аути, скасування.

    python patterns_demo.py

Сторінки віддає локальний upstream_app (:8795), тож інтернет не потрібен. Python ≥ 3.11
(TaskGroup, asyncio.timeout). Час залежить від машини.
"""
import asyncio
import time

import httpx

from serve import running

PAGES = range(1, 8)
DELAY = 0.3
received = {"count": 0}                                  # скільки відповідей отримав САМ клієнт


async def fetch(client: httpx.AsyncClient, n: int, delay: float = DELAY) -> str:
    response = await client.get(f"/page/{n}", params={"delay": delay})
    response.raise_for_status()
    received["count"] += 1
    return response.json()["title"]


async def fetch_or_fail(client: httpx.AsyncClient, n: int) -> str:
    if n == 3:
        response = await client.get("/fail/3")         # 503 через 0.1 с
        response.raise_for_status()
    return await fetch(client, n)


async def served(client: httpx.AsyncClient) -> int:
    return (await client.get("/stats")).json()["served"]


async def reset(client: httpx.AsyncClient) -> None:
    await client.post("/reset")
    received["count"] = 0


def clock(start: float) -> str:
    return f"{time.perf_counter() - start:4.2f} с"


async def sequential_vs_gather(client: httpx.AsyncClient) -> None:
    print(f"--- 1. {len(PAGES)} сторінок по {DELAY} с")
    start = time.perf_counter()
    titles = [await fetch(client, n) for n in PAGES]
    print(f"   по черзі (await у циклі):   {clock(start)}")
    start = time.perf_counter()
    titles = await asyncio.gather(*(fetch(client, n) for n in PAGES))
    print(f"   asyncio.gather:             {clock(start)}  порядок: {titles[:3]} …")


async def gather_failure(client: httpx.AsyncClient) -> None:
    print("\n--- 2. одна сторінка з 7 відповідає 503")
    await reset(client)
    start = time.perf_counter()
    try:
        await asyncio.gather(*(fetch_or_fail(client, n) for n in PAGES))
    except httpx.HTTPStatusError as error:
        print(f"   gather: виняток через {clock(start)}: {error.response.status_code}; "
              f"результатів решти сторінок немає")
    print(f"   клієнт отримав сторінок одразу після винятку: {received['count']}")
    await asyncio.sleep(0.5)
    print(f"   … і через 0.5 с: {received['count']} — решта задач працювала далі, але результати загублено")

    await reset(client)
    start = time.perf_counter()
    results = await asyncio.gather(*(fetch_or_fail(client, n) for n in PAGES), return_exceptions=True)
    ok = [r for r in results if isinstance(r, str)]
    failed = [f"{type(r).__name__}" for r in results if isinstance(r, BaseException)]
    print(f"   gather(return_exceptions=True): {clock(start)}, успішних {len(ok)}, винятків {failed}")


async def task_group(client: httpx.AsyncClient) -> None:
    print("\n--- 3. те саме через asyncio.TaskGroup")
    await reset(client)
    start = time.perf_counter()
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(fetch_or_fail(client, n)) for n in PAGES]
    except* httpx.HTTPStatusError as errors:
        print(f"   ExceptionGroup через {clock(start)}: {[e.response.status_code for e in errors.exceptions]}")
    cancelled = sum(task.cancelled() for task in tasks)
    await asyncio.sleep(0.5)
    print(f"   скасовано задач: {cancelled} з {len(tasks)}; клієнт отримав сторінок: {received['count']}")
    print(f"   а джерело все одно відпрацювало запитів: {await served(client)} — сервер не помітив, що клієнт пішов")


async def semaphore(client: httpx.AsyncClient) -> None:
    print("\n--- 4. обмежити одночасність: 12 сторінок, не більше 3 разом")
    for label, limit in [("без обмеження", None), ("asyncio.Semaphore(3)", 3)]:
        await reset(client)
        sem = asyncio.Semaphore(limit) if limit else None

        async def limited(n: int) -> str:
            if sem is None:
                return await fetch(client, n)
            async with sem:                             # 4-та задача чекає, поки одна з трьох вийде
                return await fetch(client, n)

        start = time.perf_counter()
        await asyncio.gather(*(limited(n) for n in range(1, 13)))
        peak = (await client.get("/stats")).json()["peak"]
        print(f"   {label:<32} {clock(start)}, найбільше одночасно на джерелі: {peak}")

    await reset(client)
    async with httpx.AsyncClient(base_url=client.base_url, limits=httpx.Limits(max_connections=3)) as narrow:
        start = time.perf_counter()
        await asyncio.gather(*(fetch(narrow, n) for n in range(1, 13)))
        peak = (await narrow.get("/stats")).json()["peak"]
    print(f"   {'httpx.Limits(max_connections=3)':<32} {clock(start)}, найбільше одночасно на джерелі: {peak}")


async def timeouts(client: httpx.AsyncClient) -> None:
    print("\n--- 5. тайм-аути: сторінки по 0.2, 0.4 і 3 с")
    delays = [0.2, 0.4, 3.0]

    start = time.perf_counter()
    try:
        async with asyncio.timeout(1):
            await asyncio.gather(*(fetch(client, i, d) for i, d in enumerate(delays)))
    except TimeoutError:
        print(f"   asyncio.timeout(1) на весь gather: TimeoutError через {clock(start)}, "
              "дві готові сторінки втрачено")

    async def page_or_none(i: int, d: float) -> str | None:
        try:
            return await asyncio.wait_for(fetch(client, i, d), timeout=1)
        except TimeoutError:
            return None

    start = time.perf_counter()
    results = await asyncio.gather(*(page_or_none(i, d) for i, d in enumerate(delays)))
    print(f"   wait_for(1) на кожну сторінку:     {clock(start)}, {results}")

    start = time.perf_counter()
    try:
        await client.get("/page/9", params={"delay": 3}, timeout=1)
    except httpx.TimeoutException as error:
        print(f"   тайм-аут httpx (timeout=1):         {type(error).__name__} через {clock(start)}")


async def cancellation(client: httpx.AsyncClient) -> None:
    print("\n--- 6. скасування")
    log: list[str] = []

    async def worker() -> None:
        try:
            await fetch(client, 1, 3)
        except asyncio.CancelledError:
            log.append("CancelledError на await")
            raise                                       # пробросити далі — обов'язково
        finally:
            log.append("finally: прибирання виконано")

    task = asyncio.create_task(worker())
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        log.append("той, хто чекав, теж отримав CancelledError")
    print("  ", " → ".join(log), f"| task.cancelled() = {task.cancelled()}")

    async def swallows() -> str:
        try:
            await fetch(client, 2, 3)
            return "сторінка"
        except asyncio.CancelledError:
            return "нічого"                             # помилка: скасування «з'їдено»

    start = time.perf_counter()
    try:
        async with asyncio.timeout(0.5):
            result = await swallows()
        print(f"   CancelledError проковтнуто: тайм-аут не спрацював, результат {result!r} через {clock(start)}")
    except TimeoutError:
        print("   TimeoutError")


async def as_completed(client: httpx.AsyncClient) -> None:
    print("\n--- 7. asyncio.as_completed: у порядку готовності")
    start = time.perf_counter()
    for next_done in asyncio.as_completed([fetch(client, n, d) for n, d in [(1, 0.6), (2, 0.2), (3, 0.4)]]):
        title = await next_done
        print(f"   {clock(start)}: {title}")


async def main(base: str) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=10) as client:
        await client.get("/stats")
        await sequential_vs_gather(client)
        await gather_failure(client)
        await task_group(client)
        await semaphore(client)
        await timeouts(client)
        await cancellation(client)
        await as_completed(client)


if __name__ == "__main__":
    with running("upstream_app:app", 8795) as base:
        asyncio.run(main(base))
