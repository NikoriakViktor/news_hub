"""Парсер RSS-стрічки «Української правди» (rss.py). Урок 42.

Модуль написав Claude Code (`claude -p`) за специфікацією tests/unit/test_pravda.py і правилами CLAUDE.md;
виправлення після рецензії позначено «Рецензія» (тести — tests/unit/test_pravda_review.py).
Основа ідеї — скрипт аналізу тональності `analysis_tonality_2.py` (feedparser); тут — лише stdlib.

RSS 2.0 (https://www.pravda.com.ua/rss/view_news/): <rss><channel><item> з title, link,
description (іноді в CDATA й з тегом <p>), category, pubDate (RFC 2822, +0300 або GMT).
Як і parser.py, повертає *сирі* рядки — RawNews; перевіряє їх NewsItem (models.py).
"""
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from .parser import RawNews

# База часових поясів: у Linux і macOS — системна, у Windows — лише з пакета tzdata (requirements.txt)
KYIV = ZoneInfo("Europe/Kyiv")


def _text(item: ET.Element, tag: str) -> str:
    found = item.find(tag)
    return (found.text or "").strip() if found is not None else ""


def _clean_description(raw: str) -> str:
    """CDATA іноді містить <p>…</p> — лишаємо чистий текст, без тегів."""
    return BeautifulSoup(raw, "html.parser").get_text().strip()


def _kyiv_datetime(pub_date: str) -> str:
    """RFC 2822 (+0300 чи GMT) → місцевий київський час без поясу, як datetime у RawNews rbc.ua.

    Рецензія (урок 42): порожній чи битий pubDate кидав ValueError — і губилася вся стрічка;
    тепер у такої новини просто немає часу. «-0000» дає datetime без поясу — це UTC, а не час сервера.
    """
    try:
        parsed = parsedate_to_datetime(pub_date)
    except (TypeError, ValueError):
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(KYIV).replace(tzinfo=None).isoformat()


def parse_pravda_rss(feed: str) -> list[RawNews]:
    """RSS-стрічка «Української правди» → список сирих новин без дублікатів за url (порядок стрічки)."""
    try:
        root = ET.fromstring(feed)
    except ET.ParseError as error:
        raise ValueError(f"пошкоджений RSS: {error}") from error

    news_list: list[RawNews] = []
    seen_urls: set[str] = set()
    for item in root.iter("item"):
        url = _text(item, "link")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        news_list.append({
            "title": _text(item, "title"),
            "url": url,
            "category": _text(item, "category"),
            "description": _clean_description(_text(item, "description")),
            "datetime": _kyiv_datetime(_text(item, "pubDate")),
        })
    return news_list
