"""Основи pytest: assert, межі, raises, approx, parametrize, маркер."""
import pytest

from newsapp.text import WORDS_PER_MINUTE, reading_time, shorten, slugify


def words(n: int) -> str:
    return "слово " * n


def test_two_hundred_words_take_one_minute() -> None:
    # Arrange — підготувати дані
    text = words(200)
    # Act — виконати одну дію
    minutes = reading_time(text)
    # Assert — перевірити результат
    assert minutes == 1


@pytest.mark.parametrize(("n", "minutes"), [
    (0, 0),          # порожній текст
    (1, 1),          # одне слово — вже хвилина
    (200, 1),        # рівно на межі
    (201, 2),        # на одне слово більше за межу
    (400, 2),
], ids=["empty", "one-word", "exactly-200", "just-above", "400"])
def test_reading_time_table(n: int, minutes: int) -> None:
    assert reading_time(words(n)) == minutes


def test_wpm_must_be_positive() -> None:
    with pytest.raises(ValueError, match="додатним"):
        reading_time("текст", wpm=0)


def test_wpm_one_is_allowed() -> None:
    """Межа з іншого боку: 1 — найменше дозволене значення (знайдено мутаційним тестуванням)."""
    assert reading_time(words(3), wpm=1) == 3


def test_words_per_second_is_approximate() -> None:
    assert WORDS_PER_MINUTE / 60 == pytest.approx(3.333, abs=0.001)


@pytest.mark.parametrize(("title", "slug"), [
    ("Уряд ухвалив бюджет", "уряд-ухвалив-бюджет"),
    ("  FastAPI 1.0:   що нового?  ", "fastapi-1-0-що-нового"),
    ("Курс $ / € — 2025", "курс-2025"),
], ids=["cyrillic", "spaces-and-dots", "symbols-dropped"])   # без ids pytest екранує кирилицю: \u0423…
def test_slugify(title: str, slug: str) -> None:
    assert slugify(title) == slug


def test_slugify_rejects_title_without_words() -> None:
    with pytest.raises(ValueError, match="немає слів") as error:
        slugify("?!…")
    assert "'?!…'" in str(error.value)          # у повідомленні — сам заголовок


@pytest.mark.parametrize(("title", "limit", "expected"), [
    ("Коротко", 10, "Коротко"),
    ("Рівно десять", 12, "Рівно десять"),
    ("Уряд ухвалив бюджет", 10, "Уряд ухва…"),
    ("Уряд ухвалив бюджет", 6, "Уряд…"),         # пробіл перед «…» прибрано
    ("Уряд", 1, "…"),                             # найменший дозволений limit
], ids=["short", "exactly-limit", "cut", "cut-at-space", "limit-1"])
def test_shorten(title: str, limit: int, expected: str) -> None:
    assert shorten(title, limit) == expected


def test_shorten_rejects_zero_limit() -> None:
    with pytest.raises(ValueError, match="щонайменше 1, а маємо 0"):
        shorten("Уряд", 0)


@pytest.mark.slow
def test_reading_time_of_a_huge_text() -> None:
    assert reading_time(words(2_000_000)) == 10_000
