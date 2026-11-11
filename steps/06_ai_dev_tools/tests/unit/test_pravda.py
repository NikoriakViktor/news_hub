"""Специфікація нового джерела — Українська правда (RSS). Урок 42.

Тести написано ДО коду: їх отримує AI-асистент разом із завданням «зроби, щоб проходили, тести не змінюй».
Стрічка — tests/fixtures/pravda_rss.xml (навчальний знімок у форматі RSS 2.0).
"""
from pathlib import Path

import pytest

from news_hub.models import is_allowed_host, is_rbc_host, validate_news
from news_hub.rss import parse_pravda_rss

FEED = (Path(__file__).parent.parent / "fixtures" / "pravda_rss.xml").read_text(encoding="utf-8")


def test_items_in_feed_order_without_duplicates() -> None:
    news = parse_pravda_rss(FEED)
    assert [n["url"] for n in news] == [
        "https://www.pravda.com.ua/news/2026/09/26/7501001/",
        "https://www.epravda.com.ua/news/2026/09/26/712345/",
        "https://www.pravda.com.ua/news/2026/09/26/7500990/",
        "https://www.pravda.com.ua/news/2026/09/26/7500980/",
    ]


def test_fields_are_clean_text() -> None:
    first, _, quoted, no_description = parse_pravda_rss(FEED)
    assert first == {"title": "Уряд оновив правила вступу до університетів",
                     "url": "https://www.pravda.com.ua/news/2026/09/26/7501001/",
                     "category": "Суспільство",
                     "description": "Кабінет міністрів затвердив зміни до порядку прийому.",   # без <p>
                     "datetime": "2026-09-26T21:40:00"}
    assert quoted["title"] == 'Синоптики: "Перші заморозки прийдуть у жовтні"'            # &quot; → "
    assert no_description["description"] == ""


def test_time_is_kyiv_local() -> None:
    """pubDate буває з +0300 і в GMT; у RawNews — місцевий київський час без поясу, як у rbc.ua."""
    assert [n["datetime"] for n in parse_pravda_rss(FEED)] == [
        "2026-09-26T21:40:00", "2026-09-26T20:05:00", "2026-09-26T20:15:00", "2026-09-26T19:00:00"]


def test_pipeline_rss_to_model() -> None:
    valid, rejected = validate_news(parse_pravda_rss(FEED))
    assert [(n.source, n.lang, n.category, n.published_time.isoformat() if n.published_time else None)
            for n in valid] == [
        ("pravda.com.ua", "uk", "Суспільство", "21:40:00"),
        ("epravda.com.ua", "uk", "Економіка", "20:05:00"),
        ("pravda.com.ua", "uk", "Новини", "20:15:00"),
    ]
    assert [r.raw["title"] for r in rejected] == ["Відео дня"]          # закороткий заголовок — не мовчки


@pytest.mark.parametrize(("host", "allowed"), [
    ("rbc.ua", True), ("www.rbc.ua", True), ("pravda.com.ua", True), ("www.pravda.com.ua", True),
    ("epravda.com.ua", True), ("www.epravda.com.ua", True),
    ("fakerbc.ua", False), ("fakepravda.com.ua", False), ("pravda.com.ua.evil.com", False),
    ("", False), (None, False),
])
def test_allowed_hosts(host: str | None, allowed: bool) -> None:
    assert is_allowed_host(host) is allowed


def test_scrape_request_still_accepts_only_rbc_pages() -> None:
    """Сторінки для POST /api/scrape — як і раніше, лише rbc.ua: RSS не відкриває SSRF на нові домени."""
    assert is_rbc_host("www.rbc.ua") and not is_rbc_host("www.pravda.com.ua")


def test_parser_does_not_touch_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("парсер не має ходити в мережу")

    monkeypatch.setattr(socket, "create_connection", no_network)
    assert len(parse_pravda_rss(FEED)) == 4


def test_broken_xml_raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_pravda_rss("<rss><channel><item><title>обрізано")
