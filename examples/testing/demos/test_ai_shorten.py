"""Перевірка AI-коду: тест від AI зелений, тести властивостей — червоні.

pytest demos/test_ai_shorten.py
"""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from demos.ai_shorten import shorten


def test_written_by_ai_repeats_the_implementation() -> None:
    """«Тест», який згенерував той самий асистент: очікуване значення обчислене тією ж формулою."""
    title, limit = "Уряд ухвалив бюджет", 10
    assert shorten(title, limit) == title[:limit] + "…"


@given(st.text(max_size=120), st.integers(min_value=1, max_value=150))
def test_never_exceeds_limit(title: str, limit: int) -> None:
    assert len(shorten(title, limit)) <= limit


def test_zero_limit_is_rejected() -> None:
    with pytest.raises(ValueError):
        shorten("Уряд", 0)
