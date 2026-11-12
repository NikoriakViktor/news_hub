"""Скільки часу займають N одночасних запитів — і скільки різних процесів їх обробили.

    python scripts/load.py http://127.0.0.1:18110/io 100
    python scripts/load.py "http://127.0.0.1:18110/cpu?rounds=300000" 16

Не бенчмарк: лише порівняння «один процес» і «кілька процесів» на одній машині.
"""
import asyncio
import sys
import time
from collections import Counter

import httpx


async def main(url: str, n: int) -> None:
    limits = httpx.Limits(max_connections=n, max_keepalive_connections=0)   # кожен запит — нове з'єднання
    async with httpx.AsyncClient(timeout=120, limits=limits) as client:
        await client.get(url)                                               # прогрів
        start = time.perf_counter()
        responses = await asyncio.gather(*(client.get(url) for _ in range(n)))
        elapsed = time.perf_counter() - start
    codes = Counter(r.status_code for r in responses)
    pids = Counter(r.json()["pid"] for r in responses if r.status_code == 200)
    print(f"{n} запитів: {elapsed:.2f} с, коди {dict(codes)}, процесів {len(pids)}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
