"""Мережа під моком: fetch_one без інтернету (урок 41).

Правило «patch where used» (MOCKING_AND_PATCHING.md): підміняємо ім'я там,
де його *шукає* код, що тестується. scraper.py робить `from .parser import parse_rbc_news` —
у модулі scraper з'являється власне ім'я `parse_rbc_news`, і саме його треба патчити.
"""
import asyncio
from unittest import mock

import aiohttp
import pytest

from news_hub import scraper
from tests.factories import make_raw

URL = "https://www.rbc.ua/ukr/news/"


def fake_session(html: str = "", error: BaseException | None = None) -> mock.MagicMock:
    """Замість aiohttp.ClientSession: session.get(...) — async-контекст, що віддає відповідь з html.

    error — виняток, який «кине мережа»: з raise_for_status (статус 4xx/5xx) або з самого запиту.
    """
    response = mock.MagicMock()
    response.text = mock.AsyncMock(return_value=html)
    session = mock.MagicMock()
    if isinstance(error, aiohttp.ClientResponseError):
        response.raise_for_status.side_effect = error
    elif error is not None:
        session.get.side_effect = error
    session.get.return_value.__aenter__.return_value = response
    return session


def http_error(status: int) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(request_info=mock.MagicMock(real_url=URL), history=(), status=status,
                                      message="Forbidden")


@pytest.mark.asyncio
async def test_ok_page_is_parsed() -> None:
    session = fake_session('<a href="/ukr/news/a-1.html">14:19 Уряд затвердив новий бюджет</a>')
    page, items = await scraper.fetch_one(session, URL, t0=0.0)
    assert (page.count, page.error) == (1, None)
    assert items[0]["title"] == "Уряд затвердив новий бюджет"
    session.get.assert_called_once_with(URL, headers=scraper.HEADERS, timeout=mock.ANY)   # з User-Agent


@pytest.mark.asyncio
@pytest.mark.parametrize(("error", "expected"), [
    (http_error(403), "ClientResponseError: 403"),
    (asyncio.TimeoutError(), "TimeoutError"),
    (aiohttp.ClientConnectionError("Connection reset by peer"), "ClientConnectionError: Connection reset"),
], ids=["403", "timeout", "connection-reset"])
async def test_network_errors_become_page_error(error: BaseException, expected: str) -> None:
    """Сторінка з помилкою — не виняток на весь збір, а PageResult з error і нулем новин."""
    page, items = await scraper.fetch_one(fake_session(error=error), URL, t0=0.0)
    assert (page.count, items) == (0, [])
    assert page.error is not None and page.error.startswith(expected)


@pytest.mark.asyncio
async def test_patch_where_used() -> None:
    """Одна функція — два імені: news_hub.parser.parse_rbc_news і news_hub.scraper.parse_rbc_news."""
    fake = [make_raw()]
    with mock.patch("news_hub.parser.parse_rbc_news", return_value=fake) as where_defined:
        _, items = await scraper.fetch_one(fake_session("<html></html>"), URL, t0=0.0)
    assert (where_defined.called, items) == (False, [])          # scraper цю підміну не побачив

    with mock.patch("news_hub.scraper.parse_rbc_news", return_value=fake) as where_used:
        _, items = await scraper.fetch_one(fake_session("<html></html>"), URL, t0=0.0)
    where_used.assert_called_once_with("<html></html>")
    assert items == fake


@pytest.mark.asyncio
async def test_scrape_all_async_merges_pages_without_duplicates() -> None:
    """fetch_one під моком: перевіряємо лише склеювання результатів сторінок."""
    same = make_raw(url="https://www.rbc.ua/ukr/news/same.html")
    other = make_raw(url="https://www.rbc.ua/ukr/news/other.html")

    async def fake_fetch(session: object, url: str, t0: float) -> tuple[scraper.PageResult, list[scraper.RawNews]]:
        items = [same] if url.endswith("/a/") else [same, other]
        return scraper.PageResult(url=url, start=0, end=0, count=len(items)), items

    with mock.patch("news_hub.scraper.fetch_one", side_effect=fake_fetch):
        outcome = await scraper.scrape_all_async(["https://x/a/", "https://x/b/"])
    assert [p.count for p in outcome.pages] == [1, 2]
    assert [n["url"] for n in outcome.news] == [same["url"], other["url"]]     # «same» — один раз
