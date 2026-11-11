# Крок 3. База даних: SQLAlchemy і Alembic

> **Код кроку:** [`steps/03_sqlalchemy_alembic`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/03_sqlalchemy_alembic) · відповідає уроку 39 курсу.
>
> **Передумови:** [Крок 2. Перший API на FastAPI](../02_fastapi_basics/index.md).

## Що додаємо

Новини переїжджають зі словника в пам'яті в базу: SQLAlchemy 2 async, унікальний `url`, репозиторій замість `NewsStore`, сесія на запит, повний CRUD і міграції Alembic.

## Теми кроку

1. Engine, сесії й таблиця
2. Репозиторій замість `NewsStore`
3. Сесія на запит і COMMIT до відповіді
4. Повний CRUD
5. Міграції Alembic

!!! info "Сторінки кроку — у роботі"
    Покроковий розбір цих тем з'явиться тут. Поки що — код кроку, README в його папці й теорія:
    [Частина V. Бази даних: SQLAlchemy async і Alembic](../../05_databases/README.md).

## Структура після кроку

```
news_hub/
├── news_hub/
│   ├── parser.py     ← стартовий parse_rbc_news + типи: HTML → list[RawNews]
│   ├── models.py     ← NewsItem (Pydantic), validate_news: RawNews → перевірені / відхилені
│   ├── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
│   ├── scraper.py    ← урок 38: сторінки rbc.ua через aiohttp — разом (gather) або по черзі
│   ├── db.py         ← урок 39: engine, сесії, get_db (сесія й транзакція на запит)
│   ├── tables.py     ← урок 39: NewsRow — таблиця news (SQLAlchemy 2.0)
│   ├── repository.py ← урок 39: NewsRepository — увесь SQL; замінив NewsStore з уроку 38
│   └── api.py        ← FastAPI: /api/news (+ CRUD /api/news/{id}), /stats, POST /api/scrape
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── migrations/       ← урок 39: Alembic — версії схеми бази (0001: таблиця news)
├── alembic.ini
├── docker-compose.yml ← урок 39: PostgreSQL 16 для розробки
├── postman/news_hub.postman_collection.json   ← 13 запитів з перевірками
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
└── tests/            ← pytest: моделі, парсер, знімок, API і CRUD (TestClient; SQLite або PostgreSQL)
```

Джерела коду: база й репозиторій — стартовий `production_bot/backend/core/database.py`, `repositories/base.py`, `migrations/`; API і скрапер — прототип `news_dashboard/app/main.py` і `scraper.py`; `parse_rbc_news` — ноутбук про веб-скрапінг `note_lesson_32_web_scraping.ipynb`; словник категорій — `news_dashboard/app/scraper.py`. Знімок — `rbc_news.json` поруч із тим самим ноутбуком.

## Запуск

Усі команди — з папки кроку: `cd steps/03_sqlalchemy_alembic`.

```bash
pip install -r requirements.txt
pytest                      # 32 тести на SQLite у пам'яті
mypy --strict news_hub      # перевірка типів

# база: без DATABASE_URL — файл news_hub.db (SQLite); з PostgreSQL:
docker compose up -d db
export DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub   # Windows: set DATABASE_URL=...

alembic upgrade head        # створити / оновити таблиці
uvicorn news_hub.api:app --reload
```

Ті самі тести на PostgreSQL: `TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test pytest` (базу `news_hub_test` створи заздалегідь).

- http://127.0.0.1:8000/docs — Swagger UI: спершу `POST /api/scrape` з `{"source": "snapshot"}`, потім `GET /api/news`;
- Postman: Import → `postman/news_hub.postman_collection.json` → Run collection;
- без Postman: `npx newman run postman/news_hub.postman_collection.json`.

Свіжа стрічка (коли `www.rbc.ua` доступний з мережі) — `POST /api/scrape` з `{}` або
`{"mode": "sequential"}`; у відповіді — час кожної сторінки й помилки, якщо сторінка не завантажилась.

## Порівняння з попереднім кроком

```bash
git diff --no-index --stat steps/02_fastapi_basics steps/03_sqlalchemy_alembic
git diff --no-index steps/02_fastapi_basics/news_hub steps/03_sqlalchemy_alembic/news_hub
```

## Що далі

[Крок 4. Middleware, кеш і Redis](../04_middleware_redis/index.md)
