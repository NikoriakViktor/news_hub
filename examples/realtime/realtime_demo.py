"""Перевірка realtime_app.py: SSE, Last-Event-ID, WebSocket з токеном і без, розсилка з мертвим сокетом, webhooks в OpenAPI."""
import asyncio

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from realtime_app import ConnectionManager, app

client = TestClient(app)

print("--- SSE GET /events/news")
with client.stream("GET", "/events/news") as response:
    print(response.status_code, response.headers["content-type"])
    print("".join(response.iter_text())[:230])

print("--- SSE з Last-Event-ID: 3")
with client.stream("GET", "/events/news", headers={"Last-Event-ID": "3"}) as response:
    print([line for line in response.iter_lines() if line.startswith("id:")])

print("--- SSE з yield моделі")
with client.stream("GET", "/events/plain") as response:
    print("".join(response.iter_text()).strip())

print("--- WebSocket без токена")
try:
    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_text()
except WebSocketDisconnect as exc:
    print("закрито:", exc.code, exc.reason)

print("--- WebSocket з токеном, два клієнти")
with client.websocket_connect("/ws/chat?token=secret-token") as alice, \
        client.websocket_connect("/ws/chat?token=secret-token") as bob:
    alice.send_text("привіт")
    print("alice отримала:", alice.receive_text(), "| bob отримав:", bob.receive_text())


class FakeSocket:
    """Замість справжнього з'єднання: записує повідомлення або падає, як сокет клієнта, що зник."""
    def __init__(self, name: str, dead: bool = False) -> None:
        self.name, self.dead, self.got = name, dead, []

    async def send_text(self, message: str) -> None:
        if self.dead:
            raise RuntimeError("Cannot call send once a close message has been sent")
        self.got.append(message)


async def broadcasts() -> None:
    for method in ("broadcast_naive", "broadcast"):
        manager = ConnectionManager()
        sockets = [FakeSocket("a"), FakeSocket("dead", dead=True), FakeSocket("c")]
        manager.active = list(sockets)
        try:
            await getattr(manager, method)("новина")
        except RuntimeError as exc:
            print(f"{method}: виняток {exc!r}")
        print(f"{method}: отримали {[s.name for s in sockets if s.got]}, лишились {[s.name for s in manager.active]}")

print("--- розсилка, коли один клієнт зник")
asyncio.run(broadcasts())

print("--- OpenAPI")
schema = client.get("/openapi.json").json()
print("paths:", list(schema["paths"]))
print("webhooks:", {name: list(ops) for name, ops in schema["webhooks"].items()})
print("SSE у схемі:", list(schema["paths"]["/events/news"]["get"]["responses"]["200"]["content"]))
