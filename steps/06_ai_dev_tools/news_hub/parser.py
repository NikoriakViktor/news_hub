"""Парсер стрічки новин rbc.ua.

Стартовий код — функція `parse_rbc_news` з ноутбука про web scraping.
Рефакторинг уроку 36: анотації типів, `list[dict]` → `list[RawNews]`,
пошук тегів винесено в `_find_tag`; логіку розбору не змінено.
Урок 41: прогін тестів на мінімальних версіях залежностей знайшов, що з beautifulsoup4 4.12
(requirements дозволяє) `_classes` падав на кожному тезі без атрибута class → виправлено.

Парсер повертає *сирі* рядки з HTML — перевіряє їх `NewsItem` (models.py).
"""
import re
from typing import Callable

from bs4 import BeautifulSoup, Tag
# Pydantic перевіряє TypedDict з typing лише на Python 3.12+; typing_extensions — на будь-якому
from typing_extensions import TypedDict

BASE_URL = "https://www.rbc.ua"

# Контейнери новини на сторінці: (тег, CSS-клас). Перший, що знайшовся, — використовуємо.
ITEM_SELECTORS: list[tuple[str, str]] = [
    ("div", "newsline__item"),
    ("li", "newsline__item"),
    ("div", "news-feed__item"),
    ("div", "news-item"),
    ("article", "news-item"),
    ("article", "article-item"),
]


class RawNews(TypedDict):
    """Одна новина так, як її дає HTML: лише рядки, ще не перевірені."""
    title: str
    url: str
    category: str
    description: str
    datetime: str


def _classes(tag: Tag) -> str:
    # Тег без class: beautifulsoup4 4.12 дає [None] (join падав з TypeError), новіші — [] (урок 41)
    return " ".join(cls for cls in tag.get_attribute_list("class") if cls)


def _find_tag(item: Tag, match: Callable[[Tag], bool]) -> Tag | None:
    found = item.find(match)
    return found if isinstance(found, Tag) else None


def _absolute(href: str) -> str:
    return href if href.startswith("http") else BASE_URL + href


def _parse_containers(soup: BeautifulSoup, seen_urls: set[str]) -> list[RawNews]:
    """Стратегія 1: специфічні CSS-класи контейнерів новин."""
    items: list[Tag] = []
    for tag, cls in ITEM_SELECTORS:
        found = [t for t in soup.find_all(tag, class_=cls) if isinstance(t, Tag)]
        if found:
            items = found
            break

    news_list: list[RawNews] = []
    for item in items:
        title_tag = (
            _find_tag(item, lambda t: t.name == "a" and "title" in _classes(t))
            or _find_tag(item, lambda t: t.name in ("h2", "h3"))
            or _find_tag(item, lambda t: t.name == "a")
        )
        if title_tag is None:
            continue

        title = title_tag.get_text(strip=True)
        if len(title) < 10:
            continue

        href = str(title_tag.get("href") or "")
        full_url = _absolute(href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        cat_tag = _find_tag(item, lambda t: t.name in ("span", "div", "a") and any(
            key in _classes(t) for key in ("categor", "rubric", "section")))
        category = cat_tag.get_text(strip=True) if cat_tag else ""

        desc_tag = _find_tag(item, lambda t: t.name == "p") or _find_tag(
            item, lambda t: t.name == "div" and any(k in _classes(t) for k in ("desc", "lead", "anons", "text")))
        description = desc_tag.get_text(strip=True) if desc_tag else ""
        if description == title:
            description = ""

        time_tag = _find_tag(item, lambda t: t.name == "time")
        if time_tag:
            dt = str(time_tag.get("datetime") or "") or time_tag.get_text(strip=True)
        else:
            dt_tag = _find_tag(item, lambda t: any(k in _classes(t) for k in ("date", "time", "ago")))
            dt = dt_tag.get_text(strip=True) if dt_tag else ""

        news_list.append({"title": title, "url": full_url, "category": category,
                          "description": description, "datetime": dt[:19]})
    return news_list


def _parse_links(soup: BeautifulSoup, seen_urls: set[str]) -> list[RawNews]:
    """Стратегія 2: пряме сканування посилань /news/ (текст «21:24 Заголовок»)."""
    news_list: list[RawNews] = []
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        href = str(a.get("href") or "")
        if "/news/" not in href:
            continue

        raw_text = a.get_text(separator=" ", strip=True)
        title = re.sub(r"^\d{1,2}:\d{2}\s*", "", raw_text).strip()
        if len(title) < 10:
            continue

        full_url = _absolute(href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        time_match = re.match(r"^(\d{1,2}:\d{2})", raw_text)
        news_list.append({"title": title, "url": full_url, "category": "", "description": "",
                          "datetime": time_match.group(1) if time_match else ""})
    return news_list


def parse_rbc_news(html: str) -> list[RawNews]:
    """HTML сторінки rbc.ua → список сирих новин."""
    soup = BeautifulSoup(html, "html.parser")
    seen_urls: set[str] = set()
    # Стратегія 2 — якщо контейнерів немає або вони нічого не дали
    return _parse_containers(soup, seen_urls) or _parse_links(soup, seen_urls)
