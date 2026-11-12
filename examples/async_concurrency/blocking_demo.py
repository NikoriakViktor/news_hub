"""Каскадний ефект блокуючого виклику, заміни і як блокування знайти.

    python blocking_demo.py

Запускає upstream_app (:8791) і blocking_app (:8792, потім :8793 у debug-режимі). Час залежить від машини.
"""
import asyncio
import re
import subprocess
import tempfile
import time

import httpx

from serve import running

N = 5


async def burst_with_probe(client: httpx.AsyncClient, path: str, n: int = N) -> tuple[float, float, float]:
    """n одночасних запитів до path, а поруч — /health кожні 50 мс. → (час, найгірший /health, лаг циклу)."""
    await client.get("/lag")                                   # обнулити лічильник
    worst = 0.0
    done = False

    async def probe() -> None:
        nonlocal worst
        while not done:
            start = time.perf_counter()
            await client.get("/health")
            worst = max(worst, time.perf_counter() - start)
            await asyncio.sleep(0.05)

    prober = asyncio.create_task(probe())
    start = time.perf_counter()
    await asyncio.gather(*(client.get(path) for _ in range(n)))
    elapsed = time.perf_counter() - start
    done = True
    await prober
    return elapsed, worst, (await client.get("/lag")).json()["max_lag"]


async def table(base: str, rows: list[tuple[str, str]]) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=60) as client:
        await client.get(rows[0][0])                           # прогрів: з'єднання, процеси пулу
        for path, label in rows:
            elapsed, worst, lag = await burst_with_probe(client, path)
            print(f"   {path:<13} {label:<34} {elapsed:5.2f} с | /health до {worst:4.2f} с | лаг циклу {lag:4.2f} с")


async def once(base: str, path: str) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=60) as client:
        await client.get(path)


def main() -> None:
    with running("upstream_app:app", 8791):
        with running("blocking_app:app", 8792, stderr=subprocess.DEVNULL) as base:   # журнал — у розділі 3
            print(f"--- 1. мережа: {N} одночасних запитів до джерела, що відповідає за 0.5 с")
            asyncio.run(table(base, [("/requests", "async def + requests.get"),
                                     ("/requests-def", "def + requests.get (пул потоків)"),
                                     ("/httpx", "async def + await httpx")]))
            print(f"\n--- 2. процесор: {N} одночасних обчислень")
            asyncio.run(table(base, [("/cpu", "async def + цикл обчислень"),
                                     ("/cpu-def", "def + цикл обчислень (GIL)"),
                                     ("/cpu-process", "run_in_executor(ProcessPool)")]))
            print(f"\n--- 3. bcrypt.checkpw (12 раундів): {N} одночасних входів")
            asyncio.run(table(base, [("/login", "async def + bcrypt.checkpw"),
                                     ("/login-thread", "await run_in_threadpool(checkpw)")]))

        print("\n--- 4. PYTHONASYNCIODEBUG=1: asyncio сам називає повільний крок")
        with tempfile.TemporaryFile("w+") as log:
            with running("blocking_app:app", 8793, env={"PYTHONASYNCIODEBUG": "1"}, stderr=log) as base:
                asyncio.run(once(base, "/requests"))
                asyncio.run(once(base, "/httpx"))
                time.sleep(0.3)
            log.seek(0)
            for line in log:
                if "took" in line or "запізнився" in line:
                    line = re.sub(r" created at \S+", "", line.strip())
                    print("  ", re.sub(r"/\S+/(\w+\.py)", r"\1", line)[:230])


if __name__ == "__main__":
    main()
