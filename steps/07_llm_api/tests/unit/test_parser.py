"""Парсер на збережених сторінках (tests/fixtures/*.html), а не на рядках у коді тесту.

Урок 41: HTML винесено у файли — їх видно в браузері, можна оновити, коли сайт змінить розмітку,
і один файл перевіряють і тести парсера, і тест конвеєра (test_pipeline.py).
"""
from collections.abc import Callable

import pytest

from news_hub.parser import parse_rbc_news


def test_containers_strategy(html: Callable[[str], str]) -> None:
    news = parse_rbc_news(html("demo_newsline"))
    assert [n["title"] for n in news] == ["Уряд затвердив новий бюджет на 2024 рік", "Збірна України перемогла у фіналі"]
    assert news[0] == {"title": "Уряд затвердив новий бюджет на 2024 рік", "url": "https://www.rbc.ua/ukr/news/2024/1234/",
                       "category": "Економіка", "description": "", "datetime": "2024-05-08T10:30:00"}


def test_real_rbc_markup_links_strategy(html: Callable[[str], str]) -> None:
    """Справжній фрагмент стрічки: div.item > a > span.time — контейнерів newsline__item немає."""
    assert parse_rbc_news(html("rbc_newsline_item")) == [{
        "title": "США хочуть підкупити кубинців безплатним інтернетом, - AP",
        "url": "https://www.rbc.ua/rus/news/ssha-hochut-pidkupiti-kubintsiv-bezpaltnim-1778194920.html",
        "category": "", "description": "", "datetime": "02:06"}]


def test_links_strategy_splits_time() -> None:
    html_line = '<a href="/rus/news/putina-1778325455.html">14:19 У Путіна заявили про мирну угоду</a>'
    assert parse_rbc_news(html_line) == [{"title": "У Путіна заявили про мирну угоду",
                                          "url": "https://www.rbc.ua/rus/news/putina-1778325455.html",
                                          "category": "", "description": "", "datetime": "14:19"}]


def test_page_without_news_is_empty_list() -> None:
    assert parse_rbc_news("<html><body><h1>403 Forbidden</h1></body></html>") == []


def item(inner: str) -> str:
    return f'<div class="newsline__item">{inner}</div>'


GOOD = item('<a class="title" href="/ukr/news/good-1.html">Уряд затвердив новий бюджет</a>')


@pytest.mark.parametrize(("html_page", "titles"), [
    (item("<span>без посилання й заголовка</span>") + GOOD, ["Уряд затвердив новий бюджет"]),
    (item('<a class="title" href="/ukr/news/s.html">Коротко</a>') + GOOD, ["Уряд затвердив новий бюджет"]),
    (GOOD + GOOD, ["Уряд затвердив новий бюджет"]),                              # той самий url двічі
    ('<a href="/ukr/about/">Про редакцію rbc.ua</a>'
     '<a href="/ukr/news/a.html">14:19 Ok</a>'
     '<a href="/ukr/news/b.html">Збірна перемогла у фіналі</a>'
     '<a href="/ukr/news/b.html">Збірна перемогла у фіналі</a>', ["Збірна перемогла у фіналі"]),
], ids=["no-title-tag", "short-title", "duplicate-url", "links-skip-rules"])
def test_what_parser_skips(html_page: str, titles: list[str]) -> None:
    """Гілки, які показав звіт покриття: кожне `continue` в парсері — рішення «цю новину пропустити»."""
    assert [n["title"] for n in parse_rbc_news(html_page)] == titles


def test_description_equal_to_title_is_dropped_time_from_class() -> None:
    news = parse_rbc_news(item('<h3>Уряд затвердив новий бюджет</h3><p>Уряд затвердив новий бюджет</p>'
                               '<span class="date">14:19</span>'))
    assert (news[0]["description"], news[0]["datetime"]) == ("", "14:19")
