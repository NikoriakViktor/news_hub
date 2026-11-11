"""Фейк замість моку: справжній aiohttp проти локального сервера з HTML-фікстурами (урок 41).

Мок (tests/unit/test_scraper.py) підміняє session.get — код HTTP-клієнта не виконується.
Тут працює все по-справжньому: з'єднання, заголовки, статуси, декодування байтів, тайм-аути, —
лише сервер наш, на 127.0.0.1, і відповідає миттєво. Інтернет не потрібен.
"""
import asyncio
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from news_hub import scraper

DELAY = 0.3          # «повільна» сторінка — щоб побачити різницю між gather і чергою
SEEN_AGENTS = web.AppKey("seen_agents", list[str])     # які User-Agent побачив сервер


@pytest_asyncio.fixture
async def site(html: Callable[[str], str]) -> AsyncIterator[TestServer]:
    seen_agents: list[str] = []

    async def page(name: str, request: web.Request) -> web.Response:
        seen_agents.append(request.headers.get("User-Agent", ""))
        return web.Response(text=html(name), content_type="text/html")

    async def feed(request: web.Request) -> web.Response:
        return await page("rbc_newsline_item", request)

    async def slow(request: web.Request) -> web.Response:
        await asyncio.sleep(DELAY)
        return await page("demo_newsline", request)

    async def forbidden(request: web.Request) -> web.Response:
        return web.Response(status=403, text="<h1>403 Forbidden</h1>", content_type="text/html")

    async def broken_bytes(request: web.Request) -> web.Response:       # сервер обіцяє UTF-8, а байт 0xff — ні
        body = html("rbc_newsline_item").encode() + b"<p>\xff</p>"
        return web.Response(body=body, content_type="text/html", charset="utf-8")

    app = web.Application()
    app.router.add_get("/ukr/news/", feed)
    app.router.add_get("/slow-1/", slow)
    app.router.add_get("/slow-2/", slow)
    app.router.add_get("/forbidden/", forbidden)
    app.router.add_get("/broken/", broken_bytes)
    app[SEEN_AGENTS] = seen_agents
    async with TestServer(app) as server:
        yield server


def urls(server: TestServer, *paths: str) -> list[str]:
    return [str(server.make_url(path)) for path in paths]


@pytest.mark.asyncio
async def test_real_http_round_trip(site: TestServer) -> None:
    outcome = await scraper.scrape_all_async(urls(site, "/ukr/news/"))
    assert [(p.count, p.error) for p in outcome.pages] == [(1, None)]
    assert outcome.news[0]["datetime"] == "02:06"
    assert site.app[SEEN_AGENTS] == [scraper.HEADERS["User-Agent"]]        # заголовки справді пішли


@pytest.mark.asyncio
async def test_403_is_page_error_others_survive(site: TestServer) -> None:
    outcome = await scraper.scrape_all_async(urls(site, "/forbidden/", "/ukr/news/"))
    errors = [p.error for p in outcome.pages]
    assert errors[0] is not None and errors[0].startswith("ClientResponseError: 403")
    assert (errors[1], len(outcome.news)) == (None, 1)


@pytest.mark.asyncio
async def test_undecodable_page_does_not_kill_scrape(site: TestServer) -> None:
    """Без errors="replace" у fetch_one тут був UnicodeDecodeError, і gather губив усі сторінки."""
    outcome = await scraper.scrape_all_async(urls(site, "/broken/", "/ukr/news/"))
    assert [(p.count, p.error) for p in outcome.pages] == [(1, None), (1, None)]


@pytest.mark.asyncio
async def test_gather_is_concurrent_queue_is_not(site: TestServer) -> None:
    pages = urls(site, "/slow-1/", "/slow-2/")
    together = await scraper.scrape_all_async(pages)
    one_by_one = await scraper.scrape_sequential(pages)
    assert together.total_time < 2 * DELAY <= one_by_one.total_time
    assert len(together.news) == len(one_by_one.news) == 2          # обидві сторінки — ті самі 2 новини


@pytest.mark.asyncio
async def test_timeout_is_page_error(site: TestServer, monkeypatch: pytest.MonkeyPatch) -> None:
    """Тайм-аут 15 с у тесті не чекаємо: підміняємо ClientTimeout там, де його шукає fetch_one."""
    real_timeout = scraper.aiohttp.ClientTimeout
    monkeypatch.setattr(scraper.aiohttp, "ClientTimeout", lambda total: real_timeout(total=DELAY / 3))
    outcome = await scraper.scrape_all_async(urls(site, "/slow-1/"))
    assert outcome.pages[0].error is not None and outcome.pages[0].error.startswith("TimeoutError")
