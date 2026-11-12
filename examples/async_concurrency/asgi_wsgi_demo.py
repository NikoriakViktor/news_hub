"""WSGI і ASGI: який вигляд має інтерфейс і що він означає для одночасних запитів.

    python asgi_wsgi_demo.py

Сервери запускаються окремими процесами на портах 8771–8775 і зупиняються в кінці.
"""
import asyncio
import subprocess
import sys
import time
from collections import Counter
from wsgiref.util import setup_testing_defaults

import httpx

import asgi_app
import wsgi_app
from serve import running, running_cmd

N = 5


def call_wsgi_directly() -> None:
    environ: dict = {"PATH_INFO": "/"}
    setup_testing_defaults(environ)
    captured = {}

    def start_response(status, headers):
        captured.update(status=status, headers=headers)

    body = wsgi_app.app(environ, start_response)
    print("   app(environ, start_response) → звичайний виклик функції")
    print("   environ (кілька ключів):", {k: environ[k] for k in ("REQUEST_METHOD", "PATH_INFO", "wsgi.version")})
    print("   start_response:", captured["status"], "| тіло:", body)


async def call_asgi_directly() -> None:
    inbox = [{"type": "http.request", "body": b"", "more_body": False}]
    sent = []

    async def receive():
        return inbox.pop(0)

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    coro = asgi_app.app(scope, receive, send)
    print(f"   app(scope, receive, send) → {type(coro).__name__}; виконується лише під await")
    await coro
    print("   scope:", scope)
    for message in sent:
        print("   send:", message)


async def burst(url: str, n: int = N) -> float:
    return (await burst_by_pid(url, n))[0]


async def burst_by_pid(url: str, n: int = N) -> tuple[float, Counter]:
    async with httpx.AsyncClient(timeout=30) as client:
        start = time.perf_counter()
        responses = await asyncio.gather(*(client.get(url) for _ in range(n)))
        elapsed = time.perf_counter() - start
    assert all(r.status_code == 200 for r in responses)
    return elapsed, Counter(r.text.split()[0] for r in responses)


async def statuses(url: str, n: int) -> dict[int, int]:
    async with httpx.AsyncClient(timeout=30) as client:
        responses = await asyncio.gather(*(client.get(url) for _ in range(n)))
    return dict(Counter(r.status_code for r in responses))


async def pids(url: str, n: int = 40) -> Counter:
    """Кожен запит — нове з'єднання: розподіляє їх ядро ОС між процесами, що слухають порт."""
    counter: Counter = Counter()
    for _ in range(n):
        async with httpx.AsyncClient() as client:
            counter[(await client.get(url)).text] += 1
    return counter


def main() -> None:
    print("--- 1. WSGI: застосунок — функція")
    call_wsgi_directly()
    print("\n--- 2. ASGI: застосунок — корутина і повідомлення")
    asyncio.run(call_asgi_directly())

    print(f"\n--- 3. {N} одночасних запитів, кожен чекає 0.5 с")
    with running_cmd([sys.executable, "wsgi_app.py", "8771"], 8771) as base:
        print(f"   WSGI, wsgiref, 1 потік                       {asyncio.run(burst(base + '/slow')):5.2f} с")
    with running_cmd([sys.executable, "wsgi_app.py", "8772", "threaded"], 8772) as base:
        print(f"   WSGI, wsgiref, потік на запит                {asyncio.run(burst(base + '/slow')):5.2f} с")
    with running("asgi_app:app", 8773) as base:
        print(f"   ASGI, uvicorn, 1 процес, await asyncio.sleep {asyncio.run(burst(base + '/slow')):5.2f} с")
        print(f"   ASGI, uvicorn, 1 процес, time.sleep          {asyncio.run(burst(base + '/block')):5.2f} с")

    print("\n--- 4. uvicorn --workers 2: два процеси, у кожного свій цикл подій")
    with running("asgi_app:app", 8774, "--workers", "2") as base:
        for pid, count in sorted(asyncio.run(pids(base + "/")).items()):
            print(f"   {pid}: {count} запитів з 40")
        for attempt in range(3):
            elapsed, by_pid = asyncio.run(burst_by_pid(base + "/block"))
            print(f"   {N} × time.sleep(0.5), спроба {attempt + 1}: {elapsed:5.2f} с  {dict(sorted(by_pid.items()))}")

    print("\n--- 5. uvicorn --limit-concurrency 10: ліміт рахує відкриті з'єднання")
    with running("asgi_app:app", 8775, "--limit-concurrency", "10", stderr=subprocess.DEVNULL) as base:
        for n in (8, 15):
            print(f"   {n:>2} одночасних з'єднань → коди відповідей {asyncio.run(statuses(base + '/slow', n))}")


if __name__ == "__main__":
    main()
