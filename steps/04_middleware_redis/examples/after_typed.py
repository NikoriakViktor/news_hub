"""Стало: RawNews (TypedDict) і NewsItem (Pydantic) — mypy перевіряє ключі й None."""
from news_hub.models import NewsItem
from news_hub.parser import RawNews


def headline(item: RawNews) -> str:
    return item["titel"].upper()          # та сама одруківка


def hour(item: NewsItem) -> int:
    return item.published_time.hour       # у 31 новини часу немає (None)
