"""Багато сторінок: по черзі, усі разом (gather) і з обмеженням (Semaphore, ліміти пулу)."""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import httpx
import requests

from server import start_server

BASE = start_server()
PAGES = 20                                     # кожна сторінка відповідає 0.5 с


def stats() -> str:
    data = requests.get(f"{BASE}/stats", timeout=5).json()
    requests.post(f"{BASE}/reset", timeout=5)
    return f"сервер бачив одночасно: {data['max_in_flight']}"


def report(label: str, start: float) -> None:
    print(f"{label:<40} {time.perf_counter() - start:5.1f} с   {stats()}")


requests.post(f"{BASE}/reset", timeout=5)

start = time.perf_counter()
with httpx.Client(base_url=BASE) as client:
    for n in range(PAGES):
        client.get(f"/page/{n}").raise_for_status()
report("по черзі, httpx.Client", start)

start = time.perf_counter()
with httpx.Client(base_url=BASE) as client, ThreadPoolExecutor(max_workers=5) as pool:   # один пул на всі потоки
    list(pool.map(lambda n: client.get(f"/page/{n}").raise_for_status(), range(PAGES)))
report("ThreadPoolExecutor(5), httpx.Client", start)


async def fetch(client: httpx.AsyncClient, n: int) -> dict:
    response = await client.get(f"/page/{n}")
    response.raise_for_status()
    return response.json()


async def all_at_once() -> list[dict]:
    async with httpx.AsyncClient(base_url=BASE) as client:
        return await asyncio.gather(*(fetch(client, n) for n in range(PAGES)))

start = time.perf_counter()
pages = asyncio.run(all_at_once())
report("gather, httpx.AsyncClient", start)
print("  порядок результатів = порядок задач:", [page["page"] for page in pages][:6], "…")


async def limited(limit: int) -> list[dict]:
    semaphore = asyncio.Semaphore(limit)         # не більше `limit` запитів одночасно

    async def fetch_limited(client: httpx.AsyncClient, n: int) -> dict:
        async with semaphore:
            return await fetch(client, n)

    async with httpx.AsyncClient(base_url=BASE) as client:
        return await asyncio.gather(*(fetch_limited(client, n) for n in range(PAGES)))

start = time.perf_counter()
asyncio.run(limited(5))
report("gather + Semaphore(5)", start)


async def pool_limit() -> None:
    limits = httpx.Limits(max_connections=5)    # те саме обмеження — на рівні пулу з'єднань
    async with httpx.AsyncClient(base_url=BASE, limits=limits) as client:
        await asyncio.gather(*(fetch(client, n) for n in range(PAGES)))

start = time.perf_counter()
asyncio.run(pool_limit())
report("gather + httpx.Limits(max_connections=5)", start)


async def aiohttp_limit() -> None:
    connector = aiohttp.TCPConnector(limit_per_host=5)      # за замовчуванням limit=100, limit_per_host=0
    async with aiohttp.ClientSession(base_url=BASE, connector=connector) as session:
        async def one(n: int) -> dict:
            async with session.get(f"/page/{n}") as resp:
                resp.raise_for_status()
                return await resp.json()
        await asyncio.gather(*(one(n) for n in range(PAGES)))

start = time.perf_counter()
asyncio.run(aiohttp_limit())
report("gather + aiohttp limit_per_host=5", start)


async def pool_timeout() -> None:
    """Ліміт пулу + короткий тайм-аут: задачі, що чекали вільне з'єднання, падають з PoolTimeout."""
    limits = httpx.Limits(max_connections=2)
    async with httpx.AsyncClient(base_url=BASE, limits=limits, timeout=httpx.Timeout(5, pool=0.5)) as client:
        calls = (client.get(f"/page/{n}", params={"delay": 1}) for n in range(6))
        results = await asyncio.gather(*calls, return_exceptions=True)
    print("  сторінки по 1 с, 2 з'єднання, pool=0.5:", [type(r).__name__ for r in results])

asyncio.run(pool_timeout())
stats()
