"""Знімок стрічки rbc.ua — 168 новин, зібраних `parse_rbc_news`
(файл rbc_news.json). Поки сайт недоступний
із середовища курсу, агрегатор працює на цьому знімку.
"""
import json
from pathlib import Path

from pydantic import TypeAdapter

from .parser import RawNews

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "rbc_news_snapshot.json"
_RAW_LIST = TypeAdapter(list[RawNews])       # TypedDict теж можна перевірити Pydantic-ом


def load_snapshot(path: Path = SNAPSHOT) -> list[RawNews]:
    """JSON-файл → список RawNews; неправильна структура файлу — ValidationError."""
    return _RAW_LIST.validate_python(json.loads(path.read_text(encoding="utf-8")))
