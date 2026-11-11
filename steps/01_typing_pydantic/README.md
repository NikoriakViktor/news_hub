# news_hub — новинний агрегатор (крок 1: типи і Pydantic)

Наскрізний проєкт FastAPI-гілки курсу: парсер новин → перевірені моделі → API → база → кеш → підсумки від Gemini → Telegram-бот → Docker. Кожен урок — рефакторинг проєкту попереднього.

| Урок | Крок |
|---|---|
| **37** | **стартовий парсер з анотаціями типів; `NewsItem` на Pydantic** ← ти тут |
| 38 | FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman |
| 39 | SQLAlchemy: новини в базі, унікальний `url` |
| 40 | middleware, кеш і rate limit на Redis |
| 42 | тести API (pytest + httpx) |
| 44 | Gemini: підсумок, категорія, тональність |
| 48 | Telegram-бот: `/news`, `/digest` |
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

Джерела коду: `parse_rbc_news` — ноутбук про веб-скрапінг `note_lesson_32_web_scraping.ipynb`; словник категорій — `news_dashboard/app/scraper.py`. Знімок — `rbc_news.json` поруч із тим самим ноутбуком.

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

Розбір змін — [урок 37 у книзі курсу](https://nikoriakviktor.github.io/PY-Course-Victor-Nikoriak-11-11-2026/modules/m4/lesson_37/).
