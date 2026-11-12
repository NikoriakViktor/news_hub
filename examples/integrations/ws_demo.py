"""WebSocket наживо: два сервери uvicorn на різних портах (як два воркери) і клієнт `websockets`.

    pip install -r requirements.txt
    python ws_demo.py                                   # Redis — fakeredis у пам'яті цього процесу
    REDIS_URL=redis://localhost:6379/0 python ws_demo.py   # справжній Redis

Обидва «воркери» — в одному процесі, тож спільний словник учасників грає роль бази даних.
Повідомлення між ними йдуть лише через хаб: MemoryHub (у кожного свій) або RedisHub (спільний Redis).
"""
import asyncio
import json
import os
import socket
from typing import Any

import fakeredis
import httpx
import uvicorn
from redis.asyncio import Redis
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from ws_app import Hub, MemoryHub, RedisHub, create_app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def serve(hub: Hub, members: dict[str, set[str]]) -> tuple[uvicorn.Server, asyncio.Task[None], int]:
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(hub, members), port=port, log_level="error"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    return server, task, port


async def stop(*servers: tuple[uvicorn.Server, asyncio.Task[None], int]) -> None:
    for server, task, _ in servers:
        server.should_exit = True
        await task


def show(label: str, value: object) -> None:
    print(f"   {label:<36} {value}")


async def join(port: int, token: str, origin: str = "https://news.example") -> Any:
    ws = await connect(f"ws://127.0.0.1:{port}/ws/rooms/newsroom", origin=origin)  # type: ignore[arg-type]
    await ws.send(json.dumps({"token": token}))
    return ws


async def next_event(ws: Any, timeout: float = 1.5) -> object:
    try:
        return json.loads(await asyncio.wait_for(ws.recv(), timeout))
    except asyncio.TimeoutError:
        return f"нічого за {timeout} с"
    except ConnectionClosed as closed:
        return f"закрито: {closed.rcvd.code} {closed.rcvd.reason}" if closed.rcvd else "закрито без кадру Close"


async def handshake() -> None:
    print("--- 1. рукостискання: Upgrade → 101; чужий Origin → 403 ще до WebSocket")
    a = await serve(MemoryHub(), {"newsroom": {"olena", "anna"}})
    ws = await join(a[2], "t-olena")
    show("https://news.example", f"{ws.response.status_code} {ws.response.reason_phrase}, "
                                 f"Upgrade: {ws.response.headers['Upgrade']}")
    show("перше повідомлення від сервера", await next_event(ws))
    await ws.close()
    for origin in ["https://evil.example", "https://news.example.evil.com"]:
        try:
            await join(a[2], "t-olena", origin=origin)
        except InvalidStatus as error:
            show(origin, f"HTTP {error.response.status_code}")
    for token, label in [("t-wrong", "чужий токен"), ("t-bob", "bob не в кімнаті")]:
        ws = await join(a[2], token)
        show(label, await next_event(ws))
    await stop(a)


async def workers(title: str, hub_a: Hub, hub_b: Hub) -> None:
    print(f"--- {title}")
    members = {"newsroom": {"olena", "anna"}}                    # «база» — спільна для обох воркерів
    a, b = await serve(hub_a, members), await serve(hub_b, members)
    olena, anna = await join(a[2], "t-olena"), await join(b[2], "t-anna")
    await next_event(olena), await next_event(anna)
    await asyncio.sleep(0.2)                                     # підписка на Redis встигла
    await olena.send(json.dumps({"text": "привіт з воркера A"}))
    show("olena (A) отримала", await next_event(olena))
    show("anna (B) отримала", await next_event(anna))
    async with httpx.AsyncClient() as http:
        response = await http.delete(f"http://127.0.0.1:{a[2]}/rooms/newsroom/members/anna")
    show("DELETE anna на воркері A", response.status_code)
    show("з'єднання anna на воркері B", await next_event(anna))
    try:
        await anna.send(json.dumps({"text": "я ще тут?"}))
        show("anna пише після вилучення", await next_event(anna, 0.5))
    except ConnectionClosed as closed:
        show("anna пише після вилучення", type(closed).__name__)
    await olena.close()
    await stop(a, b)


async def main() -> None:
    await handshake()
    await workers("2. два воркери, MemoryHub у кожного свій", MemoryHub(), MemoryHub())
    url = os.getenv("REDIS_URL")
    if url:
        redis_a, redis_b = Redis.from_url(url), Redis.from_url(url)
        label = f"справжній Redis {url}"
    else:
        server = fakeredis.FakeServer()
        redis_a, redis_b = fakeredis.FakeAsyncRedis(server=server), fakeredis.FakeAsyncRedis(server=server)
        label = "fakeredis"
    await workers(f"3. два воркери, RedisHub ({label})", RedisHub(redis_a), RedisHub(redis_b))
    await redis_a.aclose()
    await redis_b.aclose()


if __name__ == "__main__":
    asyncio.run(main())
