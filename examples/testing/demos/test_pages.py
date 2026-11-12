"""Один тест виконує кожен рядок page_count, але не кожну гілку."""
from demos.pages import page_count


def test_partial_last_page() -> None:
    assert page_count(25, 10) == 3
