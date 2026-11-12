"""Тести без перевірок: 100% покриття text.py — і жодної спійманої помилки.

pytest demos/test_no_asserts.py --cov=newsapp.text --cov-branch
"""
import contextlib

from newsapp.text import reading_time, shorten, slugify


def test_calls_everything() -> None:
    reading_time("слово " * 201)
    slugify("Уряд ухвалив бюджет")
    shorten("Коротко", 10)
    shorten("Уряд ухвалив бюджет", 6)
    for broken in (lambda: reading_time("x", wpm=0), lambda: slugify("?!"), lambda: shorten("x", 0)):
        with contextlib.suppress(ValueError):
            broken()
