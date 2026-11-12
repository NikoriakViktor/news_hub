"""Покриття рядків проти покриття гілок: pytest demos/test_pages.py --cov=demos.pages [--cov-branch]"""


def page_count(total: int, size: int) -> int:
    """Скільки сторінок по size новин потрібно для total новин."""
    pages = total // size
    if total % size:
        pages += 1                      # неповна остання сторінка
    return pages
