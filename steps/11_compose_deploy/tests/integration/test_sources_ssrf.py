"""Урок 46: RSS-джерела адміна і SSRF — справжній aiohttp проти локальних серверів.

`feed` — «зовнішній» сайт зі стрічкою; `internal` — «внутрішній сервіс» (як Redis, адмінка чи метадані хмари),
до якого сервер не має звертатися ніколи. Обидва на 127.0.0.1, тож у тестах політика `LOCAL` явно дозволяє
loopback, але лише порт сервера `feed` — так «внутрішній» лишається недосяжним, як у справжній мережі.
"""
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from news_hub.api import app, get_fetch_policy
from news_hub.rss import parse_pravda_rss
from news_hub.safe_fetch import FetchPolicy

FEED = (Path(__file__).parent.parent / "fixtures" / "pravda_rss.xml").read_bytes()
RSS = "application/rss+xml"
HITS = web.AppKey("hits", list[str])            # які запити дійшли до «внутрішнього» сервісу


@pytest_asyncio.fixture
async def internal() -> AsyncIterator[TestServer]:
    hits: list[str] = []

    async def secret(request: web.Request) -> web.Response:
        hits.append(request.path)
        return web.Response(body=FEED, content_type=RSS)        # навіть «схоже на RSS» — не має дійти

    server_app = web.Application()
    server_app.router.add_get("/{tail:.*}", secret)
    server_app[HITS] = hits
    async with TestServer(server_app) as server:
        yield server


@pytest_asyncio.fixture
async def feed(internal: TestServer) -> AsyncIterator[TestServer]:
    async def rss(request: web.Request) -> web.Response:
        return web.Response(body=FEED, content_type=RSS)

    async def html(request: web.Request) -> web.Response:
        return web.Response(text="<html>не стрічка</html>", content_type="text/html")

    async def huge(request: web.Request) -> web.StreamResponse:      # без Content-Length, по шматках
        response = web.StreamResponse(headers={"Content-Type": RSS})
        await response.prepare(request)
        for _ in range(40):
            await response.write(b"<!-- " + b"x" * 65_536 + b" -->")
        return response

    def redirect(target: Callable[[], str]) -> Callable[[web.Request], Awaitable[web.Response]]:
        async def handler(request: web.Request) -> web.Response:
            return web.Response(status=302, headers={"Location": target()})
        return handler

    port = 0                                   # порт стане відомий після старту сервера

    server_app = web.Application()
    server_app.router.add_get("/rss", rss)
    server_app.router.add_get("/page", html)
    server_app.router.add_get("/huge", huge)
    server_app.router.add_get("/moved", redirect(lambda: "/rss"))
    server_app.router.add_get("/to-internal", redirect(lambda: str(internal.make_url("/admin"))))
    server_app.router.add_get("/to-metadata", redirect(lambda: f"http://169.254.169.254:{port}/latest/meta-data/"))
    server_app.router.add_get("/to-file", redirect(lambda: "file:///etc/passwd"))
    server_app.router.add_get("/loop", redirect(lambda: "/loop"))
    async with TestServer(server_app) as server:
        port = server.port                     # той самий порт — щоб спрацювала перевірка IP, а не порту
        yield server


@pytest.fixture
def local_policy(feed: TestServer) -> FetchPolicy:
    policy = FetchPolicy(allow_ip=lambda ip: ip.is_loopback, allowed_ports=frozenset({feed.port}),
                         max_bytes=1_000_000)
    app.dependency_overrides[get_fetch_policy] = lambda: policy
    return policy


async def add_and_fetch(aclient: httpx.AsyncClient, url: str) -> httpx.Response:
    created = await aclient.post("/api/sources", json={"url": url, "name": "тест"})
    assert created.status_code == 201, created.text
    return await aclient.post(f"/api/sources/{created.json()['id']}/fetch")


@pytest.mark.asyncio
async def test_fetch_rss_source(aclient: httpx.AsyncClient, feed: TestServer, local_policy: FetchPolicy) -> None:
    response = await add_and_fetch(aclient, str(feed.make_url("/moved")))
    report = response.json()
    assert response.status_code == 200, report
    assert (report["redirects"], report["final_url"]) == (1, str(feed.make_url("/rss")))
    assert report["news_found"] == len(parse_pravda_rss(FEED.decode()))      # 5 <item>, один url двічі → 4
    assert report["news_saved"] == report["news_valid"] > 0
    assert (await aclient.get("/api/news/count")).json()["count"] == report["news_saved"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "reason"), [
    ("/to-internal", "порт"),                 # дозволений сайт перенаправляє на внутрішній сервіс
    ("/to-metadata", "169.254.169.254"),
    ("/to-file", "схема file"),
])
async def test_redirect_is_checked_again(aclient: httpx.AsyncClient, feed: TestServer, internal: TestServer,
                                         local_policy: FetchPolicy, path: str, reason: str) -> None:
    response = await add_and_fetch(aclient, str(feed.make_url(path)))
    assert response.status_code == 400 and reason in response.json()["detail"], response.text
    assert internal.app[HITS] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "reason"), [
    ("/page", "text/html"), ("/huge", "більша за"), ("/loop", "перенаправлень"),
])
async def test_not_a_feed_is_502(aclient: httpx.AsyncClient, feed: TestServer, local_policy: FetchPolicy,
                                 path: str, reason: str) -> None:
    response = await add_and_fetch(aclient, str(feed.make_url(path)))
    assert response.status_code == 502 and reason in response.json()["detail"], response.text


@pytest.mark.asyncio
async def test_default_policy_blocks_names_that_resolve_inside(aclient: httpx.AsyncClient,
                                                               internal: TestServer) -> None:
    """Без підміни політики: localhost проходить перевірку рядка (ім'я, порт 80), але DNS дає 127.0.0.1."""
    response = await add_and_fetch(aclient, "http://localhost/admin")
    assert response.status_code == 400 and "loopback" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
                                 "file:///etc/passwd", "https://www.pravda.com.ua:8443/rss",
                                 "http://admin:secret@www.pravda.com.ua/rss"])
async def test_unsafe_source_is_not_saved(aclient: httpx.AsyncClient, url: str) -> None:
    response = await aclient.post("/api/sources", json={"url": url, "name": "тест"})
    assert response.status_code == 400
    assert (await aclient.get("/api/sources")).json() == []


@pytest.mark.asyncio
async def test_source_crud(aclient: httpx.AsyncClient) -> None:
    body = {"url": "https://www.pravda.com.ua/rss/view_news/", "name": "Українська правда"}
    created = (await aclient.post("/api/sources", json=body)).json()
    assert (await aclient.post("/api/sources", json=body)).status_code == 409
    assert [s["url"] for s in (await aclient.get("/api/sources")).json()] == [body["url"]]
    assert (await aclient.delete(f"/api/sources/{created['id']}")).status_code == 204
    assert (await aclient.post(f"/api/sources/{created['id']}/fetch")).status_code == 404
