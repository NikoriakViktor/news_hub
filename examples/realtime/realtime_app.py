"""Потоки в FastAPI: вбудований SSE, WebSocket з автентифікацією і розсилкою, опис webhook в OpenAPI.

    python realtime_demo.py
"""
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Query, WebSocket, WebSocketDisconnect, WebSocketException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

app = FastAPI(title="Realtime")
NEWS = [{"id": i, "title": f"Новина {i}"} for i in range(1, 6)]
TOKENS = {"secret-token": "admin"}


class News(BaseModel):
    id: int
    title: str


# ---------------------------------------------------------------- SSE (FastAPI ≥ 0.135, без сторонніх пакетів)
@app.get("/events/news", response_class=EventSourceResponse)
async def news_events(last_event_id: Annotated[int, Header()] = 0) -> AsyncIterator[ServerSentEvent]:
    """Кожна новина — подія з id; після обриву браузер сам надішле Last-Event-ID і отримає лише нові."""
    yield ServerSentEvent(comment="потік новин", retry=3000)          # retry: через скільки мс перепідключатися
    for item in NEWS:
        if item["id"] > last_event_id:
            yield ServerSentEvent(data=item, event="news", id=str(item["id"]))


@app.get("/events/plain", response_class=EventSourceResponse)
async def plain_events() -> AsyncIterator[News]:
    """Звичайні об'єкти теж можна yield-ити: FastAPI перевірить їх моделлю і покладе в data: як JSON."""
    for item in NEWS[:2]:
        yield News(**item)


# ---------------------------------------------------------------- WebSocket
class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast_naive(self, message: str) -> None:
        for websocket in self.active:
            await websocket.send_text(message)                 # перший мертвий сокет зупиняє розсилку для решти

    async def broadcast(self, message: str) -> int:
        dead = []
        for websocket in list(self.active):
            try:
                await websocket.send_text(message)
            except Exception:                                  # клієнт зник, а ми ще не помітили
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)
        return len(self.active)


manager = ConnectionManager()


async def ws_user(token: Annotated[str | None, Query()] = None) -> str:
    """Браузерний WebSocket не вміє заголовок Authorization — токен приходить у query або першим повідомленням."""
    if token not in TOKENS:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
    return TOKENS[token]


@app.websocket("/ws/chat")
async def chat(websocket: WebSocket, user: Annotated[str, Depends(ws_user)]) -> None:
    await manager.connect(websocket)
    try:
        while True:
            text = await websocket.receive_text()
            await manager.broadcast(f"{user}: {text}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ---------------------------------------------------------------- Webhook: лише опис у OpenAPI
@app.webhooks.post("news-published")
def news_published(body: News) -> None:
    """Цей запит робить НАШ сервер на адресу клієнта, коли з'являється новина. Маршруту /news-published немає."""
