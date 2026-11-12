"""Локальний «чужий сайт» для прикладів HTTP-клієнтів: повільні відповіді, збої, перенаправлення, кодування.

Кожен скрипт сам запускає його у фоновому потоці (`start_server()`), тож інтернет не потрібен.
Окремо: `uvicorn server:app --port 8741`.
"""
import asyncio
import threading
import time
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

PORT = 8741
BASE = f"http://127.0.0.1:{PORT}"

app = FastAPI()
state = {"flaky": 0, "orders": 0, "in_flight": 0, "max_in_flight": 0}

NEWS = [{"id": 1, "title": "Ціни на пальне"}, {"id": 2, "title": "Погода в Києві"}]


@app.get("/news")
async def news() -> list[dict]:
    return NEWS


@app.get("/news/{news_id}")
async def one_news(news_id: int) -> dict:
    for item in NEWS:
        if item["id"] == news_id:
            return item
    return JSONResponse({"detail": f"новину {news_id} не знайдено"}, status_code=404)


@app.get("/echo")
async def echo(request: Request) -> dict:
    """Що побачив сервер: User-Agent, Accept і порт клієнта (новий порт = нове TCP-з'єднання)."""
    return {"user_agent": request.headers.get("user-agent"), "accept": request.headers.get("accept"),
            "client_port": request.client.port if request.client else None}


@app.get("/slow")
async def slow(delay: float = 3.0) -> dict:
    await asyncio.sleep(delay)
    return {"slept": delay}


@app.get("/drip")
async def drip(chunks: int = 6, every: float = 0.5) -> StreamingResponse:
    """Відповідь починається одразу, але тіло йде по байту раз на `every` секунд."""
    async def body() -> AsyncIterator[bytes]:
        for _ in range(chunks):
            await asyncio.sleep(every)
            yield b"."
    return StreamingResponse(body(), media_type="text/plain")


@app.get("/flaky")
async def flaky(fail: int = 2, retry_after: int | None = None) -> Response:
    """Перші `fail` запитів — 503 (з Retry-After, якщо задано), далі — 200."""
    state["flaky"] += 1
    if state["flaky"] <= fail:
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
        return JSONResponse({"detail": "перевантажено"}, status_code=503, headers=headers)
    return JSONResponse({"ok": True, "attempt": state["flaky"]})


@app.post("/orders")
async def create_order() -> Response:
    """Створює замовлення, але відповідає повільно: клієнт з коротким тайм-аутом не дочекається."""
    state["orders"] += 1
    await asyncio.sleep(1.5)
    return JSONResponse({"id": state["orders"]}, status_code=201)


@app.post("/reset")
async def reset() -> dict:
    state.update(flaky=0, orders=0, in_flight=0, max_in_flight=0)
    return {"ok": True}


@app.get("/stats")
async def stats() -> dict:
    return dict(state)


@app.get("/old-news")
async def old_news() -> RedirectResponse:
    return RedirectResponse("/news", status_code=301)


@app.get("/loop")
async def loop() -> RedirectResponse:
    return RedirectResponse("/loop", status_code=302)


TEXT = "Новини: ціни на пальне, погода"


@app.get("/cp1251")
async def cp1251() -> Response:
    """Старий сайт: текст у Windows-1251, і це сказано в Content-Type."""
    return Response(TEXT.encode("cp1251"), media_type="text/html; charset=windows-1251")


@app.get("/cp1251-silent")
async def cp1251_silent() -> Response:
    """Те саме, але charset у заголовку немає."""
    return Response(TEXT.encode("cp1251"), headers={"content-type": "text/html"})


@app.get("/broken")
async def broken() -> Response:
    """Обіцяє UTF-8, але один байт 0xff — не UTF-8."""
    return Response(TEXT.encode() + b" \xff", media_type="text/html; charset=utf-8")


@app.get("/big")
async def big(mb: int = 50) -> StreamingResponse:
    """Великий файл без Content-Length: шматки по 64 КБ."""
    chunk = b"x" * 65536
    async def body() -> AsyncIterator[bytes]:
        for _ in range(mb * 16):
            yield chunk
    return StreamingResponse(body(), media_type="application/octet-stream")


@app.get("/page/{n}")
async def page(n: int, delay: float = 0.5) -> dict:
    """Сторінка новин, яка відповідає `delay` с; сервер рахує, скільки запитів обробляє одночасно."""
    state["in_flight"] += 1
    state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
    try:
        await asyncio.sleep(delay)
        return {"page": n}
    finally:
        state["in_flight"] -= 1


def start_server() -> str:
    """uvicorn у фоновому потоці; повертає адресу, коли сервер уже приймає з'єднання."""
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return BASE
