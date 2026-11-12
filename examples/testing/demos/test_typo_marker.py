"""Одруківка в маркері. З --strict-markers (pytest.ini) — помилка збирання, а не тихий пропуск.

pytest demos/test_typo_marker.py
"""
import pytest


@pytest.mark.slwo
def test_huge_digest() -> None:
    assert True
