"""Один і той самий «повільний виклик» у різних видах ендпоінтів FastAPI.

    uvicorn endpoint_types_app:app --port 8781
    THREAD_LIMIT=100 uvicorn endpoint_types_app:app --port 8782   # більший пул потоків

Кожен ендпоінт чекає `d` секунд і повертає назву потоку, у якому виконувався.
"""
import asyncio
import os
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import anyio.to_thread
from fastapi import Depends, FastAPI
from fastapi.concurrency import run_in_threadpool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    limiter = anyio.to_thread.current_default_thread_limiter()
    if limit := os.getenv("THREAD_LIMIT"):
        limiter.total_tokens = int(limit)       # пул для def-ендпоінтів, def-залежностей і run_in_threadpool
    app.state.thread_limit = limiter.total_tokens
    yield


app = FastAPI(lifespan=lifespan)


def here() -> str:
    """Назва потоку і його номер: усі потоки пулу anyio звуться однаково."""
    return f"{threading.current_thread().name} #{threading.get_ident() % 10_000}"


@app.get("/async-await")
async def async_await(d: float = 1.0) -> dict[str, str]:
    await asyncio.sleep(d)                      # 1. async def + await: цикл подій вільний
    return {"thread": here()}


@app.get("/async-blocking")
async def async_blocking(d: float = 1.0) -> dict[str, str]:
    time.sleep(d)                               # 2. async def + блокуючий виклик: цикл подій стоїть
    return {"thread": here()}


@app.get("/sync-def")
def sync_def(d: float = 1.0) -> dict[str, str]:
    time.sleep(d)                               # 3. def: FastAPI виконує в пулі потоків
    return {"thread": here()}


@app.get("/async-threadpool")
async def async_threadpool(d: float = 1.0) -> dict[str, str]:
    thread = await run_in_threadpool(lambda: (time.sleep(d), here())[1])   # той самий пул, що й для def
    return {"thread": thread}


@app.get("/async-to-thread")
async def async_to_thread(d: float = 1.0) -> dict[str, str]:
    thread = await asyncio.to_thread(lambda: (time.sleep(d), here())[1])   # ІНШИЙ пул: executor циклу подій
    return {"thread": thread}


def sync_dependency() -> str:
    return here()


@app.get("/dependency")
async def dependency(dep_thread: Annotated[str, Depends(sync_dependency)]) -> dict[str, str]:
    return {"thread": here(), "dependency_thread": dep_thread}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health-sync")
def health_sync() -> dict[str, str]:
    return {"status": "ok"}                     # миттєвий, але def: йому теж потрібен вільний потік


@app.get("/limits")
async def limits() -> dict[str, int]:
    return {"anyio_thread_limit": app.state.thread_limit, "to_thread_workers": min(32, (os.cpu_count() or 1) + 4)}
