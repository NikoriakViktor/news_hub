import pytest
from pydantic import ValidationError

from news_hub.models import NewsItem, validate_news
from news_hub.parser import RawNews
from news_hub.snapshot import load_snapshot


def raw(**overrides: str) -> RawNews:
    item: RawNews = {"title": "Уряд затвердив новий бюджет", "url": "https://www.rbc.ua/ukr/news/budget-1.html",
                     "category": "", "description": "", "datetime": "14:19"}
    return {**item, **overrides}  # type: ignore[typeddict-item]


def test_fields_derived_from_url():
    news = NewsItem.from_raw(raw())
    assert (news.source, news.lang, news.category) == ("rbc.ua", "uk", "Новини")
    assert news.published_time is not None and news.published_time.hour == 14


def test_subdomain_is_parsed_not_replaced():
    news = NewsItem.from_raw(raw(url="https://auto.rbc.ua/rus/news/speka-1778085857.html"))
    assert (news.source, news.lang, news.category) == ("auto.rbc.ua", "ru", "Новини")


def test_empty_time_is_none():
    assert NewsItem.from_raw(raw(datetime="")).published_time is None


@pytest.mark.parametrize(("field", "value", "loc"), [
    ("title", "Коротко", "title"),
    ("url", "https://example.com/ukr/news/x.html", "url"),
    ("url", "не посилання", "url"),
    ("datetime", "25:99", "published_time"),
])
def test_invalid_values(field, value, loc):
    with pytest.raises(ValidationError) as error:
        NewsItem.from_raw(raw(**{field: value}))
    assert loc in {e["loc"][0] for e in error.value.errors()}


def test_model_is_frozen():
    news = NewsItem.from_raw(raw())
    with pytest.raises(ValidationError):
        news.title = "Інший заголовок новини"


def test_validate_news_keeps_rejected():
    valid, rejected = validate_news([raw(), raw(title="Коротко")])
    assert len(valid) == 1 and len(rejected) == 1
    assert rejected[0].errors[0].startswith("title:")


def test_snapshot_is_valid():
    valid, rejected = validate_news(load_snapshot())
    assert (len(valid), len(rejected)) == (168, 0)
