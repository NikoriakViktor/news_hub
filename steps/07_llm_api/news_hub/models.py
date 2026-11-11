"""Pydantic-модель новини — межа між «сирим» HTML і рештою застосунку.

Рефакторинг уроку 36: замість словника `{"title": ..., "url": ...}` без жодних гарантій —
`NewsItem`, який або перевірений, або не створений (`ValidationError`).
Далі цю модель використовують FastAPI (урок 37), база (38) і Gemini (43).

Урок 41: тест конвеєра «парсер → модель» на збереженій розмітці знайшов, що новини з контейнерів
(`<time datetime="2024-05-08T10:30:00">`) модель відхиляла: `published_time` приймав лише «HH:MM».
Покриття гілок знайшло й друге: перевірка `host.endswith("rbc.ua")` пропускала `fakerbc.ua` → `is_rbc_host`.
Урок 42: друге джерело — «Українська правда» (RSS): `is_allowed_host` (rbc.ua, pravda.com.ua, epravda.com.ua),
мова й категорія для URL без /ukr/ — зміни внесено Claude Code за специфікацією, категорію виправлено на рецензії.
"""
from datetime import datetime, time
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError, field_validator, model_validator

from .parser import RawNews

# Розділ сайту в URL → назва категорії (словник — з прототипу news_dashboard)
CATEGORIES: dict[str, str] = {
    "news": "Новини", "economic": "Економіка", "economics": "Економіка",
    "politics": "Політика", "society": "Суспільство", "sport": "Спорт",
    "world": "Світ", "technology": "Технології",
}
LANGS: dict[str, Literal["uk", "ru"]] = {"ukr": "uk", "rus": "ru"}


ALLOWED_DOMAINS: tuple[str, ...] = ("rbc.ua", "pravda.com.ua", "epravda.com.ua")


def _matches_domain(host: str, domain: str) -> bool:
    # Точний збіг або піддомен — ніколи host.endswith(domain), інакше пройшов би і fakerbc.ua
    return host == domain or host.endswith("." + domain)


def is_rbc_host(host: str | None) -> bool:
    """rbc.ua або його піддомен (www., auto.) — для POST /api/scrape: лише сторінки rbc.ua, не RSS-джерела."""
    return _matches_domain(host, "rbc.ua") if host else False


def is_allowed_host(host: str | None) -> bool:
    """Джерела, з яких новина може прийти в NewsItem: rbc.ua, pravda.com.ua, epravda.com.ua (і піддомени)."""
    return any(_matches_domain(host, domain) for domain in ALLOWED_DOMAINS) if host else False


class NewsItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    title: str = Field(min_length=10, max_length=300)
    url: HttpUrl
    source: str                      # домен без www: rbc.ua, auto.rbc.ua
    lang: Literal["uk", "ru"]        # з першої частини шляху: /ukr/ або /rus/
    category: str                    # з розділу в шляху: /ukr/news/ → «Новини»
    published_time: time | None = None

    @model_validator(mode="before")
    @classmethod
    def derive_from_url(cls, data: Any) -> Any:
        """source, lang і category, яких немає в HTML, беремо з URL — розбираючи його, а не рядком."""
        if not isinstance(data, dict) or not isinstance(data.get("url"), str):
            return data
        parts = urlsplit(data["url"])
        path = [segment for segment in parts.path.split("/") if segment]
        derived: dict[str, Any] = {"source": (parts.hostname or "").removeprefix("www.")}
        if path and path[0] in LANGS:
            derived["lang"] = LANGS[path[0]]
        elif not is_rbc_host(parts.hostname):
            derived["lang"] = "uk"          # pravda.com.ua / epravda.com.ua — завжди українською, без /ukr/
        # rbc.ua: /ukr/news/… — розділ другий; pravda.com.ua: /news/2026/09/26/… — перший (рецензія, урок 42:
        # код асистента брав другий сегмент і для правди → категорія «2026», якщо в RSS немає <category>)
        section = path[1] if is_rbc_host(parts.hostname) and len(path) > 1 else (path[0] if path else "")
        if section:
            derived["category"] = CATEGORIES.get(section, section.capitalize())
        return derived | {key: value for key, value in data.items() if value not in (None, "")}

    @field_validator("published_time", mode="before")
    @classmethod
    def time_from_iso_datetime(cls, value: Any) -> Any:
        """Стрічка дає «14:19», а атрибут <time datetime> — «2024-05-08T10:30:00»: беремо час."""
        if isinstance(value, str) and "T" in value:
            try:
                return datetime.fromisoformat(value).time()
            except ValueError:
                return value                    # хай помилку сформулює сама перевірка поля
        return value

    @field_validator("url")
    @classmethod
    def only_allowed(cls, url: HttpUrl) -> HttpUrl:
        if not is_allowed_host(url.host):
            raise ValueError("очікуємо новину з rbc.ua, pravda.com.ua або epravda.com.ua")
        return url

    @classmethod
    def from_raw(cls, raw: RawNews) -> "NewsItem":
        """Сирий рядок парсера → модель. Поле datetime — «HH:MM» зі стрічки або ISO з атрибута <time>."""
        return cls.model_validate({"title": raw["title"], "url": raw["url"],
                                   "category": raw["category"], "published_time": raw["datetime"]})


class Rejected(BaseModel):
    """Новина, яку не пропустила перевірка, і чому."""
    raw: RawNews
    errors: list[str]


def validate_news(raw_items: list[RawNews]) -> tuple[list[NewsItem], list[Rejected]]:
    """Розділяє сирі новини на перевірені й відхилені — нічого не губиться мовчки."""
    valid: list[NewsItem] = []
    rejected: list[Rejected] = []
    for raw in raw_items:
        try:
            valid.append(NewsItem.from_raw(raw))
        except ValidationError as error:
            messages = [f"{'.'.join(map(str, e['loc'])) or 'item'}: {e['msg']}" for e in error.errors()]
            rejected.append(Rejected(raw=raw, errors=messages))
    return valid, rejected
