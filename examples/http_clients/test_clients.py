"""Як тестувати код, що ходить в інші сервери, без інтернету: MockTransport, ASGITransport, локальний сервер.

pytest -q test_clients.py
"""
import asyncio

import aiohttp
import httpx
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from server import app


def titles(client: httpx.Client) -> list[str]:
    """Код, який тестуємо: отримує клієнт ззовні, а не створює сам — тож його можна підмінити."""
    response = client.get("/news")
    response.raise_for_status()
    return [item["title"] for item in response.json()]


def test_mock_transport_returns_canned_json() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"id": 1, "title": "Тест"}])

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://news.test") as client:
        assert titles(client) == ["Тест"]
    assert seen[0].url == "http://news.test/news"                 # перевіряємо й сам запит
    assert seen[0].headers["user-agent"].startswith("python-httpx/")


def test_mock_transport_simulates_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("немає з'єднання", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://news.test") as client:
        with pytest.raises(httpx.ConnectTimeout):
            titles(client)

    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(error_handler), base_url="http://news.test") as client:
        with pytest.raises(httpx.HTTPStatusError):
            titles(client)


def test_asgi_transport_calls_fastapi_app_in_process() -> None:
    async def run() -> list[str]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/news")
            return [item["title"] for item in response.json()]

    assert asyncio.run(run()) == ["Ціни на пальне", "Погода в Києві"]


def test_real_aiohttp_against_local_server() -> None:
    """Справжній aiohttp і справжній HTTP, лише сервер — наш, на 127.0.0.1 і випадковому порту."""
    async def broken(request: web.Request) -> web.Response:
        return web.Response(body=b"ok \xff", content_type="text/html", charset="utf-8")

    async def run() -> str:
        site = web.Application()
        site.router.add_get("/broken", broken)
        async with TestServer(site) as server, aiohttp.ClientSession() as session:
            async with session.get(server.make_url("/broken")) as resp:
                with pytest.raises(UnicodeDecodeError):                # мок цього б не показав
                    await resp.text()
                return await resp.text(errors="replace")

    assert asyncio.run(run()) == "ok �"
