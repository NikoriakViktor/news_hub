"""Навмисно червоні тести: як pytest показує падіння. Запуск: pytest demos/test_failures.py

Папка demos/ не входить у testpaths — звичайний `pytest` її не збирає.
"""
import pytest

from newsapp.text import reading_time, slugify


def test_dict_diff() -> None:
    article = {"slug": slugify("Уряд ухвалив бюджет"), "source": "rbc.ua", "minutes": 1}
    assert article == {"slug": "уряд-ухвалив-бюджет", "source": "rbc.ua", "minutes": 2}


def test_list_diff() -> None:
    assert [slugify(t) for t in ("Перша новина", "Друга новина")] == ["перша-новина", "друга"]


def test_did_not_raise() -> None:
    with pytest.raises(ValueError):
        reading_time("текст", wpm=1)                 # wpm=1 — дозволене значення, винятку немає


def test_raises_around_two_lines_hides_the_bug() -> None:
    """Зелений, хоча перевіряє не те: ValueError кинув slugify, а до reading_time справа не дійшла."""
    with pytest.raises(ValueError):
        slug = slugify("?!")                          # ← виняток тут
        reading_time(slug, wpm=0)                     # цей рядок не виконується


def test_without_assert_always_passes() -> None:
    reading_time("слово " * 201) == 1                # порівняння обчислено й викинуто: тест зелений


def test_float_equality() -> None:
    assert 0.1 + 0.2 == 0.3
