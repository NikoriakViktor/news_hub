"""Чекати чи рахувати: послідовно, потоки, процеси, asyncio — на двох видах роботи.

    python basics_demo.py

Числа часу залежать від машини; співвідношення між рядками — ні.
"""
import asyncio
import os
import sys
import sysconfig
import threading
import time
import tracemalloc
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

SOURCES = ["rbc", "ukrinform", "suspilne", "pravda", "unian"]
WAIT = 0.2                         # «відповідь мережі»
LIMITS = [200_000] * 4             # чотири однакові обчислення


def fetch(name: str) -> str:
    time.sleep(WAIT)               # блокуюче очікування, як у requests.get
    return f"{name}: ok"


async def fetch_async(name: str) -> str:
    await asyncio.sleep(WAIT)      # очікування, яке віддає керування циклу подій
    return f"{name}: ok"


def count_primes(limit: int) -> int:
    count = 0
    for n in range(2, limit):
        for d in range(2, int(n ** 0.5) + 1):
            if n % d == 0:
                break
        else:
            count += 1
    return count


def timed(label: str, work) -> object:
    start = time.perf_counter()
    result = work()
    print(f"   {label:<37} {time.perf_counter() - start:5.2f} с")
    return result


def rss_kb() -> int:
    """Пам'ять процесу, яку він справді займає (Linux)."""
    with open("/proc/self/status") as f:
        return next(int(line.split()[1]) for line in f if line.startswith("VmRSS"))


def vm_kb() -> int:
    """Віртуальна пам'ять: зарезервована, не обов'язково зайнята."""
    with open("/proc/self/status") as f:
        return next(int(line.split()[1]) for line in f if line.startswith("VmSize"))


# --- стан гонитви ---------------------------------------------------------------------------
counter = 0


def add_unsafe(times: int) -> None:
    global counter
    for _ in range(times):
        current = counter
        time.sleep(0)              # потік віддає GIL між «прочитати» і «записати»
        counter = current + 1


lock = threading.Lock()


def add_locked(times: int) -> None:
    global counter
    for _ in range(times):
        with lock:
            current = counter
            time.sleep(0)
            counter = current + 1


async def add_async(times: int, alock: asyncio.Lock | None = None) -> None:
    global counter
    for _ in range(times):
        if alock is None:
            current = counter
            await asyncio.sleep(0)     # await між «прочитати» і «записати» — тут перемикається цикл
            counter = current + 1
        else:
            async with alock:
                current = counter
                await asyncio.sleep(0)
                counter = current + 1


async def add_async_no_await(times: int) -> None:
    global counter
    for _ in range(times):
        current = counter
        counter = current + 1          # без await між кроками: інша корутина не втрутиться


def run_threads(target, n: int = 4, times: int = 1000) -> int:
    global counter
    counter = 0
    threads = [threading.Thread(target=target, args=(times,)) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return counter


def run_coros(make, n: int = 4) -> int:
    global counter
    counter = 0

    async def main() -> None:
        await asyncio.gather(*(make() for _ in range(n)))

    asyncio.run(main())
    return counter


# --- процеси не діляться пам'яттю --------------------------------------------------------------
seen: list[str] = []


def remember(name: str) -> int:
    seen.append(name)
    return len(seen)


# --- ціна одного виконавця ---------------------------------------------------------------------
def cost_of_threads(n: int) -> tuple[int, int]:
    stop = threading.Event()
    rss0, vm0 = rss_kb(), vm_kb()
    threads = [threading.Thread(target=stop.wait) for _ in range(n)]
    for t in threads:
        t.start()
    rss1, vm1 = rss_kb(), vm_kb()
    stop.set()
    for t in threads:
        t.join()
    return (rss1 - rss0) // n, (vm1 - vm0) // n


async def cost_of_tasks(n: int) -> int:
    stop = asyncio.Event()
    tracemalloc.start()
    before = tracemalloc.take_snapshot()
    tasks = [asyncio.create_task(stop.wait()) for _ in range(n)]
    await asyncio.sleep(0)                       # дати кожній задачі дійти до await
    after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    size = sum(stat.size_diff for stat in after.compare_to(before, "filename"))
    stop.set()
    await asyncio.gather(*tasks)
    return size // n


def main() -> None:
    print(f"Python {sys.version.split()[0]}, ядер: {os.cpu_count()}, "
          f"збірка без GIL: {bool(sysconfig.get_config_var('Py_GIL_DISABLED'))}")

    print(f"\n--- 1. робота, що ЧЕКАЄ: {len(SOURCES)} джерел по {WAIT} с")
    timed("послідовно", lambda: [fetch(s) for s in SOURCES])
    with ThreadPoolExecutor() as pool:
        timed("потоки (ThreadPoolExecutor)", lambda: list(pool.map(fetch, SOURCES)))
    with ProcessPoolExecutor(max_workers=5) as pool:
        list(pool.map(abs, range(5)))            # процеси вже запущені: міряємо роботу, не старт
        timed("процеси (ProcessPoolExecutor)", lambda: list(pool.map(fetch, SOURCES)))
    result = timed("asyncio.gather", lambda: asyncio.run(_gather()))
    print("   результат asyncio.gather:", result[0], "…", result[-1])

    print(f"\n--- 2. робота, що РАХУЄ: count_primes({LIMITS[0]}) × {len(LIMITS)}")
    timed("послідовно", lambda: [count_primes(n) for n in LIMITS])
    with ThreadPoolExecutor(max_workers=4) as pool:
        timed("потоки (GIL: по одному)", lambda: list(pool.map(count_primes, LIMITS)))
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(abs, range(4)))
        primes = timed("процеси (по ядру на процес)", lambda: list(pool.map(count_primes, LIMITS)))
    timed("asyncio.gather (корутини без await)", lambda: asyncio.run(_gather_cpu()))
    print("   простих чисел:", primes[0])

    print("\n--- 3. стан гонитви: 4 виконавці × 1000 додавань, очікуємо 4000")
    print("   потоки без Lock:                  ", run_threads(add_unsafe))
    print("   потоки з threading.Lock:          ", run_threads(add_locked))
    print("   корутини, await між кроками:      ", run_coros(lambda: add_async(1000)))
    shared = None

    def with_lock():
        nonlocal shared
        shared = shared or asyncio.Lock()
        return add_async(1000, shared)
    print("   корутини з asyncio.Lock:          ", run_coros(with_lock))
    print("   корутини без await між кроками:   ", run_coros(lambda: add_async_no_await(1000)))

    print("\n--- 4. процеси не діляться пам'яттю")
    with ProcessPoolExecutor(max_workers=1) as pool:
        print("   результати процесу:", list(pool.map(remember, ["a", "b", "c"])))
    print("   seen у головному процесі:", seen)

    print("\n--- 5. ціна одного виконавця")
    rss, vm = cost_of_threads(1000)
    print(f"   потік:  RSS +{rss} КБ, віртуальна пам'ять +{vm} КБ (стек; ulimit -s)")
    print(f"   задача asyncio: +{asyncio.run(cost_of_tasks(10_000))} Б (tracemalloc)")


async def _gather() -> list[str]:
    return await asyncio.gather(*(fetch_async(s) for s in SOURCES))


async def _primes(limit: int) -> int:
    return count_primes(limit)


async def _gather_cpu() -> list[int]:
    return await asyncio.gather(*(_primes(n) for n in LIMITS))


if __name__ == "__main__":
    main()
