# Крок 2. Перший API на FastAPI

> **Код кроку:** [`steps/02_fastapi_basics`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/02_fastapi_basics) · відповідає уроку 38 курсу.
>
> **Передумови:** [Крок 1. Типи і Pydantic](../01_typing_pydantic/index.md).

## Що додаємо

Над `NewsItem` з'являється HTTP API: `GET /api/news`, `POST /api/scrape`, сховище через `Depends` і `lifespan`, документація `/docs` і колекція Postman з перевірками.

## Теми кроку

1. FastAPI над `NewsItem`
2. Сховище через `Depends` і `lifespan`
3. `POST /api/scrape`: парсинг через API
4. OpenAPI і `/docs`
5. Postman
6. Async чи blocking: виміри

!!! info "Сторінки кроку — у роботі"
    Покроковий розбір цих тем з'явиться тут. Поки що — код кроку, README в його папці й теорія:
    [Частина III. Ядро FastAPI](../../03_fastapi_core/README.md).
    [Частина IV. Async і конкурентність](../../04_async/README.md).

## Структура після кроку

```
news_hub/
├── news_hub/
│   ├── parser.py     ← стартовий parse_rbc_news + типи: HTML → list[RawNews]
│   ├── models.py     ← NewsItem (Pydantic), validate_news: RawNews → перевірені / відхилені
│   ├── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
│   ├── scraper.py    ← урок 38: сторінки rbc.ua через aiohttp — разом (gather) або по черзі
│   ├── store.py      ← урок 38: NewsStore — сховище в пам'яті (урок 39 → SQLAlchemy)
│   └── api.py        ← урок 38: FastAPI — /api/news, /api/news/stats, POST /api/scrape
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── postman/news_hub.postman_collection.json   ← 7 запитів з перевірками
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
└── tests/            ← pytest: моделі, парсер, знімок, API (TestClient)
```

Джерела коду: API і скрапер — прототип `news_dashboard/app/main.py` і `scraper.py`; `parse_rbc_news` — ноутбук про веб-скрапінг `note_lesson_32_web_scraping.ipynb`; словник категорій — `news_dashboard/app/scraper.py`. Знімок — `rbc_news.json` поруч із тим самим ноутбуком.

## Запуск

Усі команди — з папки кроку: `cd steps/02_fastapi_basics`.

```bash
pip install -r requirements.txt
pytest                      # 23 тести
mypy --strict news_hub      # перевірка типів
uvicorn news_hub.api:app --reload
```

- http://127.0.0.1:8000/docs — Swagger UI: спершу `POST /api/scrape` з `{"source": "snapshot"}`, потім `GET /api/news`;
- Postman: Import → `postman/news_hub.postman_collection.json` → Run collection;
- без Postman: `npx newman run postman/news_hub.postman_collection.json`.

Свіжа стрічка (коли `www.rbc.ua` доступний з мережі) — `POST /api/scrape` з `{}` або
`{"mode": "sequential"}`; у відповіді — час кожної сторінки й помилки, якщо сторінка не завантажилась.

## Порівняння з попереднім кроком

```bash
git diff --no-index --stat steps/01_typing_pydantic steps/02_fastapi_basics
git diff --no-index steps/01_typing_pydantic/news_hub steps/02_fastapi_basics/news_hub
```

## Що далі

[Крок 3. База даних: SQLAlchemy і Alembic](../03_sqlalchemy_alembic/index.md)
