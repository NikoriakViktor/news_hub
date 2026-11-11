# Крок 1. Типи і Pydantic

> **Код кроку:** [`steps/01_typing_pydantic`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/01_typing_pydantic).

## Що додаємо

Стартовий парсер новин rbc.ua отримує анотації типів і `TypedDict`, а кожна новина проходить перевірку моделлю `NewsItem` на Pydantic: що не пройшло — у `rejected`, а не мовчки зникає.

## Теми кроку

1. Анотації типів і `TypedDict`
2. Pydantic: модель `NewsItem`
3. Межа довіри

!!! info "Сторінки кроку — у роботі"
    Покроковий розбір цих тем з'явиться тут. Поки що — код кроку, README в його папці й теорія:
    [Частина II. Типи і Pydantic](../../02_typing_and_pydantic/README.md).

## Структура після кроку

```
news_hub/
├── news_hub/
│   ├── parser.py     ← стартовий parse_rbc_news + типи: HTML → list[RawNews]
│   ├── models.py     ← NewsItem (Pydantic), validate_news: RawNews → перевірені / відхилені
│   └── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
└── tests/            ← pytest: моделі, парсер, знімок
```

## Запуск

Усі команди — з папки кроку: `cd steps/01_typing_pydantic`.

```bash
pip install -r requirements.txt
pytest                      # 12 тестів
mypy --strict news_hub      # перевірка типів
python -c "from news_hub.snapshot import load_snapshot; from news_hub.models import validate_news; print([len(x) for x in validate_news(load_snapshot())])"
```

Свіжу стрічку (коли `www.rbc.ua` доступний з мережі):

```python
import requests
from news_hub.parser import parse_rbc_news
from news_hub.models import validate_news

html = requests.get("https://www.rbc.ua/ukr/news/", headers={"User-Agent": "EduScraper/1.0 (course)"}, timeout=15).text
valid, rejected = validate_news(parse_rbc_news(html))
```

## Що далі

[Крок 2. Перший API на FastAPI](../02_fastapi_basics/index.md)
