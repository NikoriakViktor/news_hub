"""Блокуючі виклики в API і їхні заміни. Джерело — upstream_app на UPSTREAM (за замовчуванням :8791).

    uvicorn upstream_app:app --port 8791
    uvicorn blocking_app:app --port 8792

`/lag` — найбільша затримка циклу подій з останнього запиту до `/lag`: так блокування видно й на
сервері, де немає debug-режиму.
"""
import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager

import bcrypt
import httpx
import requests
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool

UPSTREAM = os.getenv("UPSTREAM", "http://127.0.0.1:8791")
logger = logging.getLogger("uvicorn.error")
lag = {"max": 0.0}
PASSWORD_HASH = bcrypt.hashpw(b"correct horse", bcrypt.gensalt(12))   # 12 раундів, як у hash_password


def crunch(n: int = 8_000_000) -> int:
    return sum(i * i for i in range(n))       # ≈ 0.3 с чистого процесора


async def watch_lag(interval: float = 0.05) -> None:
    """Засинає на interval і міряє, наскільки пізніше прокинулась. Запізнення = цикл був зайнятий."""
    loop = asyncio.get_running_loop()
    while True:
        start = loop.time()
        await asyncio.sleep(interval)
        late = loop.time() - start - interval
        lag["max"] = max(lag["max"], late)
        if late > 0.2:
            logger.warning("цикл подій запізнився на %.2f с", late)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.http = httpx.AsyncClient(base_url=UPSTREAM, timeout=10)     # один клієнт на процес
    app.state.processes = ProcessPoolExecutor(max_workers=4)
    watcher = asyncio.create_task(watch_lag())
    yield
    watcher.cancel()
    app.state.processes.shutdown()
    await app.state.http.aclose()


app = FastAPI(lifespan=lifespan)


@app.get("/requests")
async def with_requests(delay: float = 0.5) -> dict:
    return requests.get(f"{UPSTREAM}/page/1", params={"delay": delay}, timeout=10).json()   # блокує цикл


@app.get("/requests-def")
def with_requests_in_def(delay: float = 0.5) -> dict:
    return requests.get(f"{UPSTREAM}/page/1", params={"delay": delay}, timeout=10).json()   # потік з пулу


@app.get("/httpx")
async def with_httpx(request: Request, delay: float = 0.5) -> dict:
    response = await request.app.state.http.get("/page/1", params={"delay": delay})        # await
    return response.json()


@app.get("/cpu")
async def cpu_in_loop() -> dict:
    return {"result": crunch()}                                                          # блокує цикл


@app.get("/cpu-def")
def cpu_in_thread() -> dict:
    return {"result": crunch()}                                                          # потік, але GIL


@app.get("/cpu-process")
async def cpu_in_process(request: Request) -> dict:
    loop = asyncio.get_running_loop()
    return {"result": await loop.run_in_executor(request.app.state.processes, crunch)}   # інший процес


@app.get("/login")
async def login_in_loop() -> dict:
    return {"ok": bcrypt.checkpw(b"wrong", PASSWORD_HASH)}                              # ≈ 0.25 с у циклі


@app.get("/login-thread")
async def login_in_thread() -> dict:
    return {"ok": await run_in_threadpool(bcrypt.checkpw, b"wrong", PASSWORD_HASH)}     # bcrypt відпускає GIL


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/lag")
async def max_lag() -> dict:
    value, lag["max"] = lag["max"], 0.0
    return {"max_lag": round(value, 3)}
