"""Тести WebSocket через TestClient: без сервера й мережі, але через увесь стек FastAPI/Starlette.

    pytest -q test_ws.py
"""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ws_app import CLOSE_FORBIDDEN, CLOSE_UNAUTHORIZED, MemoryHub, create_app

GOOD = {"origin": "https://news.example"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(MemoryHub(), {"newsroom": {"olena", "anna"}}))


def join(client: TestClient, token: str, headers: dict[str, str] = GOOD):  # type: ignore[no-untyped-def]
    ws = client.websocket_connect("/ws/rooms/newsroom", headers=headers).__enter__()
    ws.send_json({"token": token})
    return ws


@pytest.mark.parametrize("origin", ["https://evil.example", "https://news.example.evil.com", None])
def test_foreign_origin_is_rejected_before_accept(client: TestClient, origin: str | None) -> None:
    headers = {"origin": origin} if origin else {}
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/ws/rooms/newsroom", headers=headers):
            pass
    assert error.value.code == 1008


def test_bad_token_closes_with_4401(client: TestClient) -> None:
    ws = join(client, "t-wrong")
    with pytest.raises(WebSocketDisconnect) as error:
        ws.receive_json()
    assert error.value.code == CLOSE_UNAUTHORIZED


def test_non_member_closes_with_4403(client: TestClient) -> None:
    ws = join(client, "t-bob")
    with pytest.raises(WebSocketDisconnect) as error:
        ws.receive_json()
    assert error.value.code == CLOSE_FORBIDDEN


def test_message_reaches_every_member(client: TestClient) -> None:
    olena, anna = join(client, "t-olena"), join(client, "t-anna")
    assert olena.receive_json()["type"] == anna.receive_json()["type"] == "hello"
    olena.send_text('{"text": "привіт"}')
    assert anna.receive_json() == {"type": "message", "user": "olena", "text": "привіт"}
    assert olena.receive_json()["text"] == "привіт"
    olena.close()
    anna.close()


def test_invalid_message_is_an_error_not_a_disconnect(client: TestClient) -> None:
    olena = join(client, "t-olena")
    olena.receive_json()
    olena.send_text('{"text": "", "admin": true}')
    assert olena.receive_json() == {"type": "error", "detail": "extra_forbidden"}
    olena.close()


def test_removed_member_is_disconnected_at_once(client: TestClient) -> None:
    olena, anna = join(client, "t-olena"), join(client, "t-anna")
    olena.receive_json()
    anna.receive_json()
    assert client.delete("/rooms/newsroom/members/anna").status_code == 204
    with pytest.raises(WebSocketDisconnect) as error:
        anna.receive_json()
    assert error.value.code == CLOSE_FORBIDDEN
    assert olena.receive_json() == {"type": "member.removed", "user": "anna"}     # решта дізнається, хто пішов
    olena.send_text('{"text": "ще тут?"}')
    assert olena.receive_json()["text"] == "ще тут?"
    olena.close()


@pytest.mark.asyncio
async def test_full_queue_of_one_client_does_not_stop_broadcast() -> None:
    hub = MemoryHub()
    async with hub.subscribe("r") as slow, hub.subscribe("r") as fast:
        slow_queue = next(iter(hub.rooms["r"]))
        while not slow_queue.full():
            slow_queue.put_nowait({"type": "old"})
        await hub.publish("r", {"type": "message", "text": "новина"})        # не кидає QueueFull
        queues = list(hub.rooms["r"])
        assert sorted(q.qsize() for q in queues) == [1, 100]
