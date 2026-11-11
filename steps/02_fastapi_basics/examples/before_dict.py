"""Було: парсер повертає list[dict] — для mypy будь-який ключ «правильний»."""


def parse() -> list[dict]:
    return [{"title": "Реформа ЗСУ", "url": "https://www.rbc.ua/rus/news/reforma-zsu", "datetime": ""}]


def headline(item: dict) -> str:
    return item["titel"].upper()          # одруківка в ключі


def hour(item: dict) -> int:
    return int(item["datetime"][:2])      # "" → ValueError, але mypy мовчить
