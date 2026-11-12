"""Фонові задачі: що насправді робить BackgroundTasks, і що додає черга (надійна черга на Redis власноруч:
повтори, «мертві» задачі, ідемпотентність, падіння воркера).

    python background_jobs_demo.py                                    # fakeredis
    REDIS_URL=redis://localhost:6390/0 python background_jobs_demo.py  # справжній Redis

Розділ 4 (перезапуск сервера) запускає справжній uvicorn у дочірньому процесі на порту 18765.
"""
import asyncio
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
import uuid

import fakeredis
import httpx
from fastapi import BackgroundTasks, FastAPI, status
from redis.asyncio import Redis
from starlette.types import Message

REDIS_URL = os.getenv("REDIS_URL", "fakeredis://")
SERVER = fakeredis.FakeServer()


def make_redis() -> Redis:
    if REDIS_URL.startswith("fakeredis"):
        return fakeredis.FakeAsyncRedis(server=SERVER, decode_responses=True)
    return Redis.from_url(REDIS_URL, decode_responses=True)


def section(title: str) -> None:
    print(f"--- {title}")


# 1–3. BackgroundTasks зсередини --------------------------------------------------------------------------

events: list[str] = []
T0 = 0.0


def mark(text: str) -> None:
    events.append(f"{(time.perf_counter() - T0) * 1000:5.0f} ms  {text}")


app = FastAPI()


async def slow_task(name: str) -> None:
    mark(f"задача {name}: старт")
    await asyncio.sleep(0.3)
    mark(f"задача {name}: кінець")


async def failing_task() -> None:
    mark("задача fail: старт")
    raise RuntimeError("джерело недоступне")


def blocking_sync_task() -> None:
    time.sleep(0.3)                     # звичайна def — FastAPI виконає в пулі потоків


async def blocking_async_task() -> None:
    time.sleep(0.3)                     # блокує цикл подій: так не можна в async def


@app.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def create_job(background: BackgroundTasks, scenario: str = "ok") -> dict[str, str]:
    if scenario == "ok":
        background.add_task(slow_task, "A")
        background.add_task(slow_task, "B")
    elif scenario == "fail-first":
        background.add_task(failing_task)
        background.add_task(slow_task, "after-fail")
    elif scenario == "block-sync":
        background.add_task(blocking_sync_task)
    elif scenario == "block-async":
        background.add_task(blocking_async_task)
    mark("ендпоінт повернув 202")
    return {"job_id": "demo"}


@app.get("/ping")
async def ping() -> dict[str, bool]:
    return {"ok": True}


async def call_asgi(path: str, query: str = "") -> str:
    """Виклик ASGI напряму: видно, коли саме сервер відправив відповідь, а коли завершився виклик."""
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": query.encode(), "root_path": "",
             "headers": [(b"host", b"api")], "client": ("1.2.3.4", 1), "server": ("api", 80), "state": {}}

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            mark(f"клієнт отримав статус {message['status']}")

    try:
        await app(scope, receive, send)
        mark("виклик ASGI завершився")
        return "ok"
    except Exception as error:
        mark(f"виклик ASGI завершився винятком {type(error).__name__}: {error}")
        return "error"


async def background_inside() -> None:
    global T0
    section("1. BackgroundTasks: відповідь іде одразу, задачі — після неї, по черзі")
    events.clear()
    T0 = time.perf_counter()
    await call_asgi("/jobs", "scenario=ok")
    print("\n".join(events))

    section("2. виняток у першій задачі: клієнт уже отримав 202, друга задача не запускається")
    events.clear()
    T0 = time.perf_counter()
    await call_asgi("/jobs", "scenario=fail-first")
    print("\n".join(events))

    section("3. блокуючий код у задачі: def проти async def — скільки чекає інший запит")
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        for scenario in ("block-sync", "block-async"):
            start = time.perf_counter()

            async def other_request() -> float:
                await asyncio.sleep(0.05)                     # за 50 ms задача вже працює
                await client.get("/ping")
                return (time.perf_counter() - start) * 1000 - 50

            _, waited = await asyncio.gather(client.post("/jobs", params={"scenario": scenario}), other_request())
            print(f"{scenario:12} GET /ping чекав відповіді: {waited:.0f} ms")


# 4. Перезапуск сервера посеред задачі ----------------------------------------------------------------

SERVER_CODE = textwrap.dedent("""
    import asyncio, sys
    from fastapi import BackgroundTasks, FastAPI
    app = FastAPI()
    async def job(seconds: float) -> None:
        print("задача: старт", flush=True)
        await asyncio.sleep(seconds)
        print("задача: кінець", flush=True)
    @app.post("/jobs", status_code=202)
    async def create(background: BackgroundTasks, seconds: float = 2) -> dict[str, str]:
        background.add_task(job, seconds)
        return {"status": "queued"}
""")


def restart_server(sig: signal.Signals, extra: list[str]) -> None:
    workdir = os.path.dirname(os.path.abspath(__file__))
    module = os.path.join(workdir, "_bg_server.py")
    with open(module, "w", encoding="utf-8") as file:
        file.write(SERVER_CODE)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "_bg_server:app", "--port", "18765", "--log-level",
                             "warning", *extra], cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)
    try:
        for _ in range(50):
            try:
                httpx.get("http://127.0.0.1:18765/docs", timeout=0.5)
                break
            except httpx.HTTPError:
                time.sleep(0.1)
        assert proc.poll() is None, "uvicorn не запустився"
        response = httpx.post("http://127.0.0.1:18765/jobs", params={"seconds": 2})
        time.sleep(0.3)
        start = time.perf_counter()
        proc.send_signal(sig)
        proc.wait(timeout=15)
        output = proc.stdout.read().splitlines() if proc.stdout else []
        lines = [line.strip() for line in output if line.startswith(("задача", "ERROR:    Cancel"))]
        if any("CancelledError" in line for line in output):
            lines.append("… CancelledError у задачі")
        print(f"{sig.name:7} {' '.join(extra) or '(за замовчуванням)':34} відповідь {response.status_code}; "
              f"процес завершився за {time.perf_counter() - start:.1f} с; вивід: {lines}")
    finally:
        if proc.poll() is None:
            proc.kill()
        os.remove(module)


def restarts() -> None:
    section("4. сервер зупиняють посеред 2-секундної задачі")
    restart_server(signal.SIGTERM, [])
    restart_server(signal.SIGTERM, ["--timeout-graceful-shutdown", "1"])
    restart_server(signal.SIGKILL, [])


# 5–7. Надійна черга на Redis ---------------------------------------------------------------------------

QUEUE, PROCESSING, DEAD = "demo:q:ready", "demo:q:processing", "demo:q:dead"


async def enqueue(r: Redis, kind: str, payload: dict[str, object], key: str | None = None) -> str:
    task = {"id": uuid.uuid4().hex[:8], "kind": kind, "payload": payload, "attempt": 0, "key": key}
    await r.lpush(QUEUE, json.dumps(task))
    return str(task["id"])


async def take(r: Redis) -> tuple[str, dict[str, object]] | None:
    """Забрати задачу так, щоб вона не зникла, якщо воркер помре: LMOVE ready → processing (атомарно)."""
    raw = await r.lmove(QUEUE, PROCESSING, "RIGHT", "LEFT")
    return (raw, json.loads(raw)) if raw else None


async def ack(r: Redis, raw: str) -> None:
    await r.lrem(PROCESSING, 1, raw)


async def requeue_stuck(r: Redis) -> int:
    """«Прибиральник»: задачі, які воркер узяв і не підтвердив (воркер помер), — назад у чергу."""
    moved = 0
    while await r.lmove(PROCESSING, QUEUE, "RIGHT", "LEFT"):
        moved += 1
    return moved


async def queue_demo() -> None:
    r = make_redis()
    await r.delete(QUEUE, PROCESSING, DEAD, "demo:sent", "demo:done:news-42")

    section("5. воркер помер з задачею в руках: BLPOP-стиль проти LMOVE + processing")
    await r.lpush("demo:q:simple", "задача 1")
    await r.rpop("demo:q:simple")                          # воркер узяв і… процес убили
    print("проста черга (RPOP): у черзі", await r.llen("demo:q:simple"), "— задача пропала")
    await enqueue(r, "notify", {"news_id": 42})
    await take(r)                                          # узяв і помер, ack не було
    print("надійна черга: ready =", await r.llen(QUEUE), "processing =", await r.llen(PROCESSING))
    print("прибиральник повернув у чергу:", await requeue_stuck(r), "| ready =", await r.llen(QUEUE))
    await r.delete(QUEUE, PROCESSING)

    section("6. повтори з паузою й «мертві» задачі")
    calls = {"flaky": 0}

    async def flaky(payload: dict[str, object]) -> None:
        calls["flaky"] += 1
        if calls["flaky"] < 3:
            raise ConnectionError("сайт не відповів")

    async def broken(payload: dict[str, object]) -> None:
        raise ValueError("сторінка змінила розмітку")

    handlers = {"flaky": flaky, "broken": broken}
    max_attempts, base_delay = 3, 0.05

    async def work_once() -> bool:
        item = await take(r)
        if item is None:
            return False
        raw, task = item
        task["attempt"] = int(task["attempt"]) + 1          # type: ignore[call-overload]
        try:
            await handlers[str(task["kind"])](task["payload"])  # type: ignore[arg-type]
            print(f"   {task['kind']}: спроба {task['attempt']} — успіх")
        except Exception as error:
            if task["attempt"] >= max_attempts:
                await r.lpush(DEAD, json.dumps({**task, "error": repr(error)}))
                print(f"   {task['kind']}: спроба {task['attempt']} — {error}; у dead-чергу")
            else:
                delay = base_delay * 2 ** (int(task["attempt"]) - 1)   # type: ignore[call-overload]
                print(f"   {task['kind']}: спроба {task['attempt']} — {error}; повтор через {delay * 1000:.0f} ms")
                await asyncio.sleep(delay)                   # у справжніх чергах — відкладена задача, не sleep
                await r.lpush(QUEUE, json.dumps(task))
        await ack(r, raw)
        return True

    await enqueue(r, "flaky", {})
    await enqueue(r, "broken", {})
    while await work_once():
        pass
    print("dead-черга:", [json.loads(x)["kind"] for x in await r.lrange(DEAD, 0, -1)])

    section("7. ідемпотентність: та сама задача прийшла двічі (повтор після таймауту, подвійний клік)")

    async def notify_naive(news_id: int) -> None:
        await r.rpush("demo:sent", f"сповіщення про новину {news_id}")

    async def notify_idempotent(news_id: int, key: str) -> bool:
        if not await r.set(f"demo:done:{key}", "1", nx=True, ex=24 * 3600):
            return False                                    # уже робили — нічого не повторюємо
        await r.rpush("demo:sent", f"сповіщення про новину {news_id}")
        return True

    for _ in range(2):
        await notify_naive(42)
    print("без ключа: надіслано", await r.llen("demo:sent"), "сповіщення")
    await r.delete("demo:sent")
    print("з ключем news-42:", [await notify_idempotent(42, "news-42") for _ in range(2)],
          "| надіслано", await r.llen("demo:sent"))

    await r.delete(QUEUE, PROCESSING, DEAD, "demo:sent", "demo:done:news-42", "demo:q:simple")
    await r.aclose()


if __name__ == "__main__":
    asyncio.run(background_inside())
    restarts()
    asyncio.run(queue_demo())
