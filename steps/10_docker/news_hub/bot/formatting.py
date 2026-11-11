"""Текст для Telegram у режимі parse_mode=HTML. Урок 47.

Основа — `app/utils/text.py` і `app/utils/formatter.py` зі стартового `ai_bot` (`escape_html`,
`split_long_message`). Рефакторинг:
- **усе**, що прийшло ззовні (ім'я користувача, заголовок новини, ключове слово), екранується перед тим,
  як потрапити в HTML: Telegram відхиляє повідомлення з «<» чи «&» поза тегом — і бот мовчить;
- адреса в `<a href="…">` — з екрануванням лапок (`quote=True`);
- довге повідомлення ділиться по **рядках**, а не кожні N символів: розріз посеред `<b>…</b>` чи `&amp;`
  дав би дві невалідні частини. Кожен рядок ми складаємо самі — він завжди цілий HTML.
"""
import html
import re

MAX_MESSAGE = 4096          # ліміт Telegram на текст одного повідомлення


def esc(text: str) -> str:
    """Текст → безпечний для HTML Telegram: & < > (лапки поза атрибутом не потрібні)."""
    return html.escape(text, quote=False)


def link(url: str, title: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{esc(title)}</a>'


def split_message(lines: list[str], limit: int = MAX_MESSAGE) -> list[str]:
    """Рядки → частини ≤ limit, розріз лише між рядками. Рядок, довший за limit, обрізається як текст."""
    parts: list[str] = []
    current = ""
    for line in lines:
        if len(line) > limit:
            line = line[: limit - 1] + "…"          # лише для рядків без розмітки (ми їх такими не складаємо)
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            parts.append(current)
            current = line
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


KEYWORD = re.compile(r"^[\w'’-]{2,40}$")
WORD = re.compile(r"[\w'’-]+")


def normalize_keyword(raw: str) -> str | None:
    """Одне слово 2–40 символів (літери, цифри, апостроф, дефіс), без регістру; інакше None."""
    word = raw.strip().casefold()
    return word if KEYWORD.fullmatch(word) else None


def matches(keyword: str, title: str) -> bool:
    """Слово заголовка ПОЧИНАЄТЬСЯ з ключового: «бюджет» знаходить «бюджету», але не «наддбюджет».

    Українська змінює закінчення, тож точний збіг слова пропускав би більшість новин, а пошук підрядка
    будь-де («рада» в «зрада») давав би хибні збіги.
    """
    return any(word.startswith(keyword) for word in WORD.findall(title.casefold()))
