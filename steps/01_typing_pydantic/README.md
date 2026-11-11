# news_hub — новинний агрегатор (крок 1: типи і Pydantic)

Наскрізний проєкт книги: парсер новин → перевірені моделі → API → база → кеш → підсумки від Gemini → Telegram-бот → Docker. Кожен крок — рефакторинг проєкту попереднього.

| Крок | Що додається |
|---|---|
| **1** | **стартовий парсер з анотаціями типів; `NewsItem` на Pydantic** ← ти тут |
| 2 | FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman |
| 3 | SQLAlchemy: новини в базі, унікальний `url` |
| 4 | middleware, кеш і rate limit на Redis |
| 5 | тести API (pytest + httpx) |
| 7 | Gemini: підсумок, категорія, тональність |
| 9 | Telegram-бот: `/news`, `/digest` |
| 48–50 | Docker, Compose, CI/CD |

## Що тут

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

Розбір змін — [Крок 1 у книзі](https://nikoriakviktor.github.io/news_hub/tutorials/01_typing_pydantic/).
