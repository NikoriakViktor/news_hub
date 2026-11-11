"""Завантаження сторінок rbc.ua: паралельно (`asyncio.gather`) або по черзі.

Стартовий код — `app/scraper.py` прототипу `news_dashboard`.
Рефакторинг уроку 37:
- власний `_parse_page` (друга копія парсера зі своїм словником категорій) → `parse_rbc_news` з уроку 36;
- NLP при парсингі прибрано — аналіз тексту повернеться в уроці 43 (Gemini);
- словники з результатами → моделі `PageResult` / `ScrapeOutcome`.

Урок 41: тест на фейковому сервері знайшов, що сторінка з одним невалідним байтом UTF-8 валила
`resp.text()` (UnicodeDecodeError — не ClientError), а з нею — `asyncio.gather` і весь збір:
новини решти сторінок губилися. Тепер такі байти замінюються на «�», а сторінка парситься.
Мок цього не бачив: його `text()` одразу повертає готовий рядок, декодування не відбувається.
"""
import asyncio
import time

import aiohttp
from pydantic import BaseModel

from .parser import RawNews, parse_rbc_news

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EduScraper/1.0; +educational)",
    "Accept-Language": "uk,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}

PAGES = [
    "https://www.rbc.ua/",
    "https://www.rbc.ua/rus/news/",
    "https://www.rbc.ua/rus/economic/",
    "https://www.rbc.ua/rus/politics/",
    "https://www.rbc.ua/rus/society/",
    "https://www.rbc.ua/ukr/news/",
    "https://www.rbc.ua/ukr/economic/",
]


class PageResult(BaseModel):
    """Одна сторінка: коли почали й закінчили (с від старту), скільки новин, чи була помилка."""
    url: str
    start: float
    end: float
    count: int
    error: str | None = None


class ScrapeOutcome(BaseModel):
    pages: list[PageResult]
    news: list[RawNews]           # без дублікатів за url
    total_time: float


async def fetch_one(session: aiohttp.ClientSession, url: str, t0: float) -> tuple[PageResult, list[RawNews]]:
    start = time.perf_counter() - t0
    error = None
    items: list[RawNews] = []
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            html = await resp.text(errors="replace")   # один битий байт ≠ втрачена сторінка
        items = parse_rbc_news(html)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        error = f"{type(e).__name__}: {e}"
    end = time.perf_counter() - t0
    return PageResult(url=url, start=round(start, 3), end=round(end, 3), count=len(items), error=error), items


def _outcome(results: list[tuple[PageResult, list[RawNews]]], t0: float) -> ScrapeOutcome:
    news: list[RawNews] = []
    seen: set[str] = set()
    for _, items in results:
        for item in items:
            if item["url"] not in seen:
                seen.add(item["url"])
                news.append(item)
    return ScrapeOutcome(pages=[page for page, _ in results], news=news,
                         total_time=round(time.perf_counter() - t0, 3))


async def scrape_all_async(pages: list[str] | None = None) -> ScrapeOutcome:
    """Усі сторінки одночасно: загальний час ≈ час найповільнішої."""
    t0 = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*(fetch_one(session, url, t0) for url in pages or PAGES))
    return _outcome(list(results), t0)


async def scrape_sequential(pages: list[str] | None = None) -> ScrapeOutcome:
    """По черзі — для порівняння: загальний час ≈ сума всіх."""
    t0 = time.perf_counter()
    async with aiohttp.ClientSession() as session:
        results = [await fetch_one(session, url, t0) for url in pages or PAGES]
    return _outcome(results, t0)
