"""Pydantic-модель новини — межа між «сирим» HTML і рештою застосунку.

Рефакторинг уроку 36: замість словника `{"title": ..., "url": ...}` без жодних гарантій —
`NewsItem`, який або перевірений, або не створений (`ValidationError`).
Далі цю модель використовують FastAPI (урок 37), база (38) і Gemini (43).
"""
from datetime import time
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
        if len(path) > 1:
            derived["category"] = CATEGORIES.get(path[1], path[1].capitalize())
        return derived | {key: value for key, value in data.items() if value not in (None, "")}

    @field_validator("url")
    @classmethod
    def only_rbc(cls, url: HttpUrl) -> HttpUrl:
        if not (url.host or "").endswith("rbc.ua"):
            raise ValueError("очікуємо новину з rbc.ua")
        return url

    @classmethod
    def from_raw(cls, raw: RawNews) -> "NewsItem":
        """Сирий рядок парсера → модель. Поле datetime зі стрічки — це лише «HH:MM»."""
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
