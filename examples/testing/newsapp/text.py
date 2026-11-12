"""Чисті функції без бази й мережі — на них основи pytest."""
import math
import re

WORDS_PER_MINUTE = 200


def reading_time(text: str, wpm: int = WORDS_PER_MINUTE) -> int:
    """Хвилини читання, округлені вгору: 1 слово — 1 хв, 201 слово при 200 сл/хв — 2 хв, порожньо — 0."""
    if wpm <= 0:
        raise ValueError(f"wpm має бути додатним, а маємо {wpm}")
    return math.ceil(len(text.split()) / wpm)


def slugify(title: str) -> str:
    """'Уряд ухвалив бюджет-2025!' → 'уряд-ухвалив-бюджет-2025'."""
    words = re.findall(r"\w+", title.lower())
    if not words:
        raise ValueError(f"у заголовку немає слів: {title!r}")
    return "-".join(words)


def shorten(title: str, limit: int) -> str:
    """Заголовок не довший за limit символів; обрізаний закінчується на «…»."""
    if limit < 1:
        raise ValueError(f"limit має бути щонайменше 1, а маємо {limit}")
    if len(title) <= limit:
        return title
    return title[: limit - 1].rstrip() + "…"
