"""Черга arq: задача — у Redis, виконує окремий воркер; статус, повтори, той самий job_id не ставиться двічі.

Потрібен справжній Redis (arq не працює з fakeredis):

    REDIS_URL=redis://localhost:6390/0 python arq_demo.py

Воркер тут запускається в тому самому процесі в режимі burst (виконати все з черги й зупинитися),
щоб демо було одним файлом. У застосунку воркер — окремий процес: `arq module.WorkerSettings`.
"""
import asyncio
import os
import signal
import subprocess
import sys
import time
from typing import Any

from arq import Retry, create_pool
from arq.connections import RedisSettings
from arq.jobs import Job
from arq.worker import Worker

REDIS_URL = os.getenv("REDIS_URL", "")
attempts: dict[str, int] = {}


async def scrape(ctx: dict[str, Any], source: str) -> dict[str, Any]:
    """Сайт відповідає з третьої спроби: Retry(defer=…) — повторити пізніше, не займаючи воркер."""
    attempts[source] = ctx["job_try"]
    if ctx["job_try"] < 3:
        raise Retry(defer=0.2)
    return {"source": source, "news_saved": 168, "tries": ctx["job_try"]}


async def broken(ctx: dict[str, Any]) -> None:
    raise ValueError("сторінка змінила розмітку")


async def long_job(ctx: dict[str, Any]) -> str:
    """Довга задача: позначає в Redis кожен свій старт."""
    await ctx["redis"].rpush("demo:arq:starts", f"спроба {ctx['job_try']}")
    await asyncio.sleep(1.5)
    return "зібрано"


def run_worker_forever() -> None:
    """`python arq_demo.py --worker` — окремий процес-воркер, як `arq module.WorkerSettings`."""
    worker = Worker(functions=[long_job], redis_settings=RedisSettings.from_dsn(REDIS_URL), job_timeout=2,
                    poll_delay=0.05)
    worker.run()


async def starts(pool: Any) -> list[str]:
    return [item.decode() for item in await pool.lrange("demo:arq:starts", 0, -1)]


async def killed_worker(pool: Any, settings: RedisSettings) -> None:
    print("--- 4. воркер убили (SIGKILL) посеред задачі")
    await pool.delete("demo:arq:starts")
    job = await pool.enqueue_job("long_job", _job_id="long:1")
    assert job is not None
    proc = subprocess.Popen([sys.executable, __file__, "--worker"], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    while not await pool.llen("demo:arq:starts"):
        await asyncio.sleep(0.05)
    proc.send_signal(signal.SIGKILL)
    proc.wait()
    print("після SIGKILL: статус", (await job.status()).value, "| старти:", await starts(pool))
    start = time.perf_counter()
    worker = Worker(functions=[long_job], redis_settings=settings, burst=True, poll_delay=0.2, job_timeout=2,
                    handle_signals=False)
    await worker.main()
    await worker.close()
    print(f"новий воркер: статус {(await job.status()).value} через {time.perf_counter() - start:.0f} с"
          f" | старти: {await starts(pool)} | результат: {await job.result(timeout=1)}")
    await pool.delete("demo:arq:starts", f"arq:result:{job.job_id}")


async def main() -> None:
    if not REDIS_URL.startswith("redis://"):
        raise SystemExit("потрібен REDIS_URL=redis://…  (див. README)")
    settings = RedisSettings.from_dsn(REDIS_URL)
    pool = await create_pool(settings)
    old = [key async for key in pool.scan_iter("arq:*")]            # залишки попереднього запуску демо
    if old:
        await pool.delete(*old)

    print("--- 1. постановка в чергу: відповідь API не чекає виконання")
    job = await pool.enqueue_job("scrape", "rbc", _job_id="scrape:rbc")
    assert job is not None
    print("job_id:", job.job_id, "| статус:", (await job.status()).value)
    again = await pool.enqueue_job("scrape", "rbc", _job_id="scrape:rbc")
    print("той самий _job_id ще раз →", again, "(дубль не поставлено)")
    failing = await pool.enqueue_job("broken")
    assert failing is not None

    print("--- 2. воркер (окремий процес у житті; тут — burst у тому самому процесі)")
    worker = Worker(functions=[scrape, broken], redis_settings=settings, burst=True, poll_delay=0.05,
                    max_tries=5, keep_result=60, handle_signals=False)
    await worker.main()
    await worker.close()
    print("спроб scrape:", attempts["rbc"], "| статус:", (await job.status()).value)
    print("результат:", await job.result(timeout=1))
    info = await Job(failing.job_id, pool).result_info()
    assert info is not None
    print("broken: success =", info.success, "| result =", repr(info.result), "| job_try =", info.job_try)
    print("воркер: виконано", worker.jobs_complete, "| з помилкою", worker.jobs_failed, "| повторів", worker.jobs_retried)

    print("--- 3. після виконання результат живе keep_result секунд — той самий _job_id знову не ставиться")
    print("enqueue scrape:rbc →", await pool.enqueue_job("scrape", "rbc", _job_id="scrape:rbc"))
    await pool.delete(f"arq:result:{job.job_id}", f"arq:result:{failing.job_id}")
    await killed_worker(pool, settings)
    await pool.aclose()


if __name__ == "__main__":
    if "--worker" in sys.argv:
        run_worker_forever()
    else:
        asyncio.run(main())
