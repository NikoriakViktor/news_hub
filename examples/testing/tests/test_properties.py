"""Тести властивостей (Hypothesis): правила, що виконуються для будь-яких входів."""
import re

from hypothesis import given
from hypothesis import strategies as st

from newsapp.text import shorten, slugify

titles = st.text(min_size=0, max_size=120)
limits = st.integers(min_value=1, max_value=150)


@given(titles, limits)
def test_shorten_never_exceeds_limit(title: str, limit: int) -> None:
    assert len(shorten(title, limit)) <= limit


@given(titles, limits)
def test_shorten_keeps_short_titles_and_marks_cut_ones(title: str, limit: int) -> None:
    result = shorten(title, limit)
    if len(title) <= limit:
        assert result == title
    else:
        assert result.endswith("…") and title.startswith(result[:-1])


@given(st.text(alphabet=st.characters(categories=["L", "N", "Zs", "P"]), min_size=1, max_size=80)
       .filter(lambda t: re.search(r"\w", t)))
def test_slugify_is_url_safe_and_idempotent(title: str) -> None:
    slug = slugify(title)
    assert re.fullmatch(r"\w+(-\w+)*", slug)
    assert slugify(slug) == slug
