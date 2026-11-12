"""Що FastAPI робить з `async def`, `def` і блокуючим викликом — виміри на справжньому uvicorn.

    python endpoint_types_demo.py

Сервери на портах 8781 і 8782 запускаються й зупиняються самі. Час залежить від машини.
"""
import asyncio
import time

import httpx

from serve import running

LIMITS = httpx.Limits(max_connections=None, max_keepalive_connections=None)


async def burst(client: httpx.AsyncClient, path: str, n: int) -> tuple[float, int]:
    start = time.perf_counter()
    responses = await asyncio.gather(*(client.get(path) for _ in range(n)))
    threads = {r.json()["thread"] for r in responses}
    return time.perf_counter() - start, len(threads)


async def latency(client: httpx.AsyncClient, path: str) -> float:
    start = time.perf_counter()
    await client.get(path)
    return time.perf_counter() - start


async def where(base: str) -> None:
    async with httpx.AsyncClient(base_url=base) as client:
        print(f"   ліміти: {(await client.get('/limits')).json()}")
        for path in ("/async-await", "/async-blocking", "/sync-def", "/async-threadpool", "/async-to-thread",
                     "/dependency"):
            print(f"   {path:<18} {(await client.get(path, params={'d': 0})).json()}")


async def measure(base: str, rows: list[tuple[str, int]]) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=120, limits=LIMITS) as client:
        await client.get("/health")
        for path, n in rows:
            elapsed, threads = await burst(client, path, n)
            print(f"   {path:<18} × {n:>3}: {elapsed:5.2f} с, різних потоків: {threads}")


async def starvation(base: str) -> None:
    """40 повільних def зайняли весь пул — що з іншими ендпоінтами?"""
    async with httpx.AsyncClient(base_url=base, timeout=120, limits=LIMITS) as client:
        await client.get("/health")
        busy = asyncio.gather(*(client.get("/sync-def", params={"d": 2}) for _ in range(40)))
        await asyncio.sleep(0.3)                 # пул уже зайнятий
        print(f"   /health      (async def) під час 40 × /sync-def: {await latency(client, '/health'):5.2f} с")
        print(f"   /health-sync (def)       під час 40 × /sync-def: {await latency(client, '/health-sync'):5.2f} с")
        await busy


def main() -> None:
    with running("endpoint_types_app:app", 8781) as base:
        print("--- 1. де виконується кожен ендпоінт (d=0)")
        asyncio.run(where(base))
        print("\n--- 2. одночасні запити, кожен чекає 1 с")
        asyncio.run(measure(base, [("/async-await", 100), ("/async-blocking", 5), ("/sync-def", 60),
                                   ("/async-threadpool", 60), ("/async-to-thread", 60)]))
        print("\n--- 3. пул зайнятий: хто чекає")
        asyncio.run(starvation(base))
    with running("endpoint_types_app:app", 8782, env={"THREAD_LIMIT": "100"}) as base:
        print("\n--- 4. THREAD_LIMIT=100 (total_tokens лімітера anyio)")
        asyncio.run(measure(base, [("/sync-def", 60), ("/async-threadpool", 60), ("/async-to-thread", 60)]))


if __name__ == "__main__":
    main()
