"""Чат кімнат на WebSocket у FastAPI: Origin, автентифікація першим повідомленням, права на кожне повідомлення,
розсилка через «хаб» — у пам'яті процесу або через Redis Pub/Sub (кілька воркерів).

    uvicorn ws_app:app                    # MemoryHub
    REDIS_URL=redis://localhost:6379/0 uvicorn ws_app:app --workers 2   # RedisHub

Розбір — сторінка книги «WebSocket у FastAPI» (Частина IX). Демо — ws_demo.py, тести — test_ws.py.
"""
import asyncio
import contextlib
import json
import logging
import os
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from redis.asyncio import Redis

logger = logging.getLogger("ws_app")

ALLOWED_ORIGINS = frozenset({"https://news.example", "http://localhost:8000", "http://127.0.0.1:8000"})
TOKENS = {"t-olena": "olena", "t-anna": "anna", "t-bob": "bob"}          # у справжньому застосунку — JWT
AUTH_TIMEOUT = 5.0                                                     # секунд на перше повідомлення

# Коди закриття 4000–4999 — для застосунку (RFC 6455, §7.4.2): клієнт за ними розуміє, що перепідключатися марно
CLOSE_UNAUTHORIZED, CLOSE_FORBIDDEN = 4401, 4403


class ChatIn(BaseModel):
    """Кожне вхідне повідомлення — через Pydantic, як тіло POST."""
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)


class Hub(Protocol):
    async def publish(self, room: str, event: dict[str, Any]) -> None: ...

    def subscribe(self, room: str) -> contextlib.AbstractAsyncContextManager[AsyncIterator[dict[str, Any]]]: ...


class MemoryHub:
    """Черга на кожне з'єднання — у пам'яті ОДНОГО процесу. Другий воркер про ці черги не знає."""

    def __init__(self) -> None:
        self.rooms: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def publish(self, room: str, event: dict[str, Any]) -> None:
        for queue in list(self.rooms[room]):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:                     # повільний клієнт не зупиняє розсилку решті
                logger.warning("кімната %s: черга клієнта повна, подію пропущено", room)

    @contextlib.asynccontextmanager
    async def subscribe(self, room: str) -> AsyncIterator[AsyncIterator[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.rooms[room].add(queue)

        async def events() -> AsyncIterator[dict[str, Any]]:
            while True:
                yield await queue.get()

        try:
            yield events()
        finally:
            self.rooms[room].discard(queue)


class RedisHub:
    """Redis Pub/Sub: PUBLISH chat:<room> бачать підписники в усіх процесах. Лише JSON — об'єкти Python не пройдуть."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def publish(self, room: str, event: dict[str, Any]) -> None:
        await self.redis.publish(f"chat:{room}", json.dumps(event, ensure_ascii=False))

    @contextlib.asynccontextmanager
    async def subscribe(self, room: str) -> AsyncIterator[AsyncIterator[dict[str, Any]]]:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"chat:{room}")

        async def events() -> AsyncIterator[dict[str, Any]]:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is not None:
                    yield json.loads(message["data"])

        try:
            yield events()
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()


def create_app(hub: Hub, members: dict[str, set[str]] | None = None) -> FastAPI:
    app = FastAPI()
    app.state.members = members if members is not None else {"newsroom": {"olena", "anna"}}

    def is_member(room: str, user: str) -> bool:
        return user in app.state.members.get(room, set())

    @app.delete("/rooms/{room}/members/{user}", status_code=status.HTTP_204_NO_CONTENT)
    async def remove_member(room: str, user: str) -> None:
        """HTTP змінює права — і відкриті WebSocket дізнаються про це одразу, через той самий хаб."""
        if not is_member(room, user):
            raise HTTPException(404, "немає такого учасника")
        app.state.members[room].discard(user)
        await hub.publish(room, {"type": "member.removed", "user": user})

    @app.websocket("/ws/rooms/{room}")
    async def room_ws(websocket: WebSocket, room: str) -> None:
        # 1. Звідки. Браузер завжди ставить Origin сторінки, і сторінка його не підробить.
        origin = websocket.headers.get("origin")
        if origin not in ALLOWED_ORIGINS:
            logger.warning("відхилено Origin %r", origin)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)   # до accept → HTTP 403
            return
        await websocket.accept()
        # 2. Хто. Токен — першим повідомленням, а не в URL: адреси пишуться в журнали доступу.
        try:
            first = await asyncio.wait_for(websocket.receive_json(), AUTH_TIMEOUT)
            user = TOKENS[first["token"]]
        except (asyncio.TimeoutError, KeyError, TypeError, ValueError):
            await websocket.close(code=CLOSE_UNAUTHORIZED, reason="unauthorized")
            return
        # 3. Чи можна в цю кімнату.
        if not is_member(room, user):
            await websocket.close(code=CLOSE_FORBIDDEN, reason="not a member")
            return
        await websocket.send_json({"type": "hello", "user": user, "room": room})

        async with hub.subscribe(room) as events:
            async def pump() -> None:
                """Хаб → цей сокет. Подія «вилучено мене» закриває з'єднання, не чекаючи мого повідомлення."""
                async for event in events:
                    if event["type"] == "member.removed" and event["user"] == user:
                        await websocket.close(code=CLOSE_FORBIDDEN, reason="removed")
                        return
                    await websocket.send_json(event)

            pump_task = asyncio.create_task(pump())
            try:
                while True:
                    raw = await websocket.receive_text()
                    # 4. Права — на КОЖНЕ повідомлення: з'єднання живе годинами, а членство змінюється.
                    if not is_member(room, user):
                        await websocket.close(code=CLOSE_FORBIDDEN, reason="not a member")
                        return
                    try:
                        message = ChatIn.model_validate_json(raw)
                    except ValidationError as error:
                        await websocket.send_json({"type": "error", "detail": error.errors()[0]["type"]})
                        continue
                    await hub.publish(room, {"type": "message", "user": user, "text": message.text})
            except (WebSocketDisconnect, RuntimeError):      # клієнт пішов або сокет закрив pump()
                pass
            finally:
                pump_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, RuntimeError, WebSocketDisconnect):
                    await pump_task

    return app


def default_hub() -> Hub:
    url = os.getenv("REDIS_URL")
    return RedisHub(Redis.from_url(url)) if url else MemoryHub()


app = create_app(default_hub())
