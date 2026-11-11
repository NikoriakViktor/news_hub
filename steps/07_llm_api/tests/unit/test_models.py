import pytest
from pydantic import ValidationError

from news_hub.models import NewsItem, is_rbc_host, validate_news
from news_hub.snapshot import load_snapshot
from tests.factories import make_raw


def test_fields_derived_from_url():
    news = NewsItem.from_raw(make_raw())
    assert (news.source, news.lang, news.category) == ("rbc.ua", "uk", "Новини")
    assert news.published_time is not None and news.published_time.hour == 14


def test_subdomain_is_parsed_not_replaced():
    news = NewsItem.from_raw(make_raw(url="https://auto.rbc.ua/rus/news/speka-1778085857.html"))
    assert (news.source, news.lang, news.category) == ("auto.rbc.ua", "ru", "Новини")


def test_empty_time_is_none():
    assert NewsItem.from_raw(make_raw(datetime="")).published_time is None


@pytest.mark.parametrize(("field", "value", "loc"), [
    ("title", "Коротко", "title"),
    ("url", "https://example.com/ukr/news/x.html", "url"),
    ("url", "https://www.fakerbc.ua/ukr/news/x.html", "url"),       # урок 41: endswith("rbc.ua") його пропускав
    ("url", "не посилання", "url"),
    ("datetime", "25:99", "published_time"),
])
def test_invalid_values(field, value, loc):
    with pytest.raises(ValidationError) as error:
        NewsItem.from_raw(make_raw(**{field: value}))
    assert loc in {e["loc"][0] for e in error.value.errors()}


def test_model_is_frozen():
    news = NewsItem.from_raw(make_raw())
    with pytest.raises(ValidationError):
        news.title = "Інший заголовок новини"


def test_validate_news_keeps_rejected():
    valid, rejected = validate_news([make_raw(), make_raw(title="Коротко")])
    assert len(valid) == 1 and len(rejected) == 1
    assert rejected[0].errors[0].startswith("title:")


def test_snapshot_is_valid():
    valid, rejected = validate_news(load_snapshot())
    assert (len(valid), len(rejected)) == (168, 0)


@pytest.mark.parametrize(("value", "expected"), [
    ("14:19", "14:19:00"),
    ("2024-05-08T10:30:00", "10:30:00"),       # атрибут <time datetime> — знайдено тестом конвеєра (урок 41)
    ("", None),
])
def test_published_time_formats(value, expected):
    news = NewsItem.from_raw(make_raw(datetime=value))
    assert (news.published_time.isoformat() if news.published_time else None) == expected


def test_broken_iso_datetime_is_rejected():
    with pytest.raises(ValidationError) as error:
        NewsItem.from_raw(make_raw(datetime="2024-13-45T99:99:00"))
    assert error.value.errors()[0]["loc"] == ("published_time",)


@pytest.mark.parametrize(("host", "allowed"), [
    ("rbc.ua", True), ("www.rbc.ua", True), ("auto.rbc.ua", True),
    ("fakerbc.ua", False), ("rbc.ua.evil.com", False), ("", False), (None, False),
])
def test_is_rbc_host(host: str | None, allowed: bool) -> None:
    """Межові значення: і те, що має пройти, і те, що «майже» rbc.ua."""
    assert is_rbc_host(host) is allowed
