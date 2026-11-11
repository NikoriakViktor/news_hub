"""Конвеєр парсер → модель на збережених сторінках.

Тести парсера перевіряють лише парсер, тести моделі — лише модель, кожен на своїх даних.
Цей тест з'єднує їх на справжній розмітці: те, що дає парсер, модель має прийняти.
"""
from collections.abc import Callable

import pytest

from news_hub.models import validate_news
from news_hub.parser import parse_rbc_news


@pytest.mark.parametrize(("page", "expected"), [
    ("rbc_newsline_item", [("США хочуть підкупити кубинців безплатним інтернетом, - AP", "ru", "02:06:00")]),
    ("demo_newsline", [("Уряд затвердив новий бюджет на 2024 рік", "uk", "10:30:00"),
                       ("Збірна України перемогла у фіналі", "uk", "09:15:00")]),
])
def test_every_parsed_item_passes_the_model(html: Callable[[str], str], page: str,
                                            expected: list[tuple[str, str, str]]) -> None:
    valid, rejected = validate_news(parse_rbc_news(html(page)))
    assert rejected == []
    assert [(n.title, n.lang, n.published_time.isoformat() if n.published_time else "") for n in valid] == expected
