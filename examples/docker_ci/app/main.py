"""Маленький застосунок для прикладів Частини X: образ, Compose, сервер, воркери.

    uvicorn main:app --port 8000

/health    — «процес живий» (для HEALTHCHECK)
/whoami    — хто обробив запит: PID, UID, IP клієнта, схема, посилання з url_for
/io        — очікування (як запит до бази чи іншого сервісу): ?seconds=0.2
/cpu       — обчислення (як стиснення, хешування паролів): тримає GIL
/job       — фонова задача BackgroundTasks: що з нею стається при зупинці
/visits    — лічильник у Redis (REDIS_URL); для прикладу Compose і томів
"""
import asyncio
import hashlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Request

log = logging.getLogger("uvicorn.error")      # логер uvicorn: пише в stderr, видно в `docker logs`


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("app startup: pid=%s uid=%s", os.getpid(), os.getuid())
    app.state.redis = None
    if url := os.getenv("REDIS_URL"):
        from redis.asyncio import Redis  # потрібен лише прикладу Compose

        app.state.redis = Redis.from_url(url)
    yield
    if app.state.redis is not None:
        await app.state.redis.aclose()
    log.info("app shutdown: connections closed")   # цей рядок видно лише при коректній зупинці


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/whoami")
async def whoami(request: Request) -> dict[str, object]:
    return {
        "pid": os.getpid(),
        "uid": os.getuid(),
        "client": request.client.host if request.client else None,
        "scheme": request.url.scheme,
        "url_for": str(request.url_for("whoami")),
        "root_path": request.scope.get("root_path", ""),
    }


@app.get("/io")
async def io(seconds: float = 0.2) -> dict[str, object]:
    await asyncio.sleep(seconds)                 # event loop вільний: інші запити йдуть паралельно
    return {"pid": os.getpid(), "slept": seconds}


@app.get("/cpu")
def cpu(rounds: int = 300_000) -> dict[str, object]:
    digest = b"news"
    for _ in range(rounds):                      # чистий Python: GIL не відпускається
        digest = hashlib.sha256(digest).digest()
    return {"pid": os.getpid(), "digest": digest.hex()[:8]}


async def slow_job(seconds: float) -> None:
    log.info("job started: %s s", seconds)
    await asyncio.sleep(seconds)
    log.info("job done")                         # не надрукується, якщо процес убито раніше


@app.post("/job", status_code=202)
async def job(background: BackgroundTasks, seconds: float = 5) -> dict[str, object]:
    background.add_task(slow_job, seconds)       # виконується в цьому ж процесі ПІСЛЯ відповіді
    return {"accepted": True, "seconds": seconds}


@app.get("/visits")
async def visits(request: Request) -> dict[str, object]:
    redis = request.app.state.redis
    if redis is None:
        return {"visits": None, "detail": "REDIS_URL не задано"}
    return {"visits": await redis.incr("visits")}
