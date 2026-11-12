"""Найменший ASGI-застосунок без FastAPI: корутина, що обмінюється з сервером повідомленнями.

    uvicorn asgi_app:app --port 8773
    uvicorn asgi_app:app --port 8774 --workers 2

FastAPI (через Starlette) — це така сама корутина `app(scope, receive, send)`, лише значно більша.
"""
import asyncio
import os
import time


async def app(scope, receive, send):
    if scope["type"] == "lifespan":              # старт і зупинка процесу: тут FastAPI запускає lifespan
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] != "http":
        return
    await receive()                              # {"type": "http.request", "body": b"", ...}
    if scope["path"] == "/slow":
        await asyncio.sleep(0.5)                 # чекає, не займаючи цикл подій
    elif scope["path"] == "/block":
        time.sleep(0.5)                          # займає цикл подій цього процесу
    body = f"pid={os.getpid()}".encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"text/plain"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})
