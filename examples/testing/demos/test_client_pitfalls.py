"""Пастки TestClient. pytest demos/test_client_pitfalls.py

1. TestClient(app) без with — lifespan не запущено, app.state порожній.
2. raise_server_exceptions=True (за замовчуванням) — виняток застосунку летить у тест, відповіді 500 немає.
3. httpx.ASGITransport lifespan не запускає — та сама порожня app.state.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from newsapp.api import app, get_mailer


class BrokenMailer:
    def send(self, to: str, subject: str, body: str) -> str:
        raise RuntimeError("SMTP пароль: hunter2")


def test_without_with_no_lifespan() -> None:
    client = TestClient(app)
    assert client.post("/digest", json={"subscribers": ["olena@example.com"]}).status_code == 200


def test_server_exception_reaches_the_test() -> None:
    app.dependency_overrides[get_mailer] = BrokenMailer
    try:
        with TestClient(app) as client:
            client.post("/articles", json={"title": "Уряд ухвалив бюджет", "source": "rbc.ua"})
            assert client.post("/digest", json={"subscribers": ["olena@example.com"]}).status_code == 500
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_asgi_transport_without_lifespan() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/articles/будь-що")).status_code == 404
