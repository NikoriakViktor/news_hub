# Крок 4. Middleware, кеш і Redis

> **Код кроку:** [`steps/04_middleware_redis`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/04_middleware_redis).
>
> **Передумови:** [Крок 3. База даних: SQLAlchemy і Alembic](../03_sqlalchemy_alembic/index.md).

## Що додаємо

Код навколо кожного запиту (middleware), кеш стрічки в Redis, rate limit з `429` і `Retry-After`, фоновий збір новин з відповіддю `202` і статусом задачі.

## Теми кроку

1. Middleware
2. Кеш стрічки в Redis
3. Rate limit: `429` і `Retry-After`
4. Фоновий збір: `202` і статус задачі

!!! info "Сторінки кроку — у роботі"
    Покроковий розбір цих тем з'явиться тут. Поки що — код кроку, README в його папці й теорія:
    [Частина VI. Middleware, кеш і фонові задачі](../../06_middleware_cache_jobs/README.md).

## Структура після кроку

```
news_hub/
├── news_hub/
│   ├── parser.py     ← стартовий parse_rbc_news + типи: HTML → list[RawNews]
│   ├── models.py     ← NewsItem (Pydantic), validate_news: RawNews → перевірені / відхилені
│   ├── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
│   ├── scraper.py    ← крок 2: сторінки rbc.ua через aiohttp — разом (gather) або по черзі
│   ├── db.py         ← крок 3: engine, сесії, get_db (сесія й транзакція на запит)
│   ├── tables.py     ← крок 3: NewsRow — таблиця news (SQLAlchemy 2.0)
│   ├── repository.py ← крок 3: NewsRepository — увесь SQL; замінив NewsStore з кроку 2
│   ├── cache.py      ← крок 4: клієнт Redis, NewsCache (cache-aside з версією)
│   ├── middleware.py ← крок 4: X-Request-ID / X-Process-Time, rate limit → 429, інвалідація кешу
│   ├── jobs.py       ← крок 4: фоновий збір, статус задачі в Redis
│   └── api.py        ← FastAPI: /api/news (+ CRUD, кеш), /stats, POST /api/scrape, /api/scrape/jobs
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── migrations/       ← крок 3: Alembic — версії схеми бази (0001: таблиця news)
├── alembic.ini
├── docker-compose.yml ← PostgreSQL 16 (крок 3) і Redis 7 (крок 4) для розробки
├── postman/news_hub.postman_collection.json   ← 16 запитів з перевірками
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
└── tests/            ← pytest: моделі, парсер, API, CRUD, Redis (TestClient; SQLite/PostgreSQL, fakeredis/Redis)
```

## Запуск

Усі команди — з папки кроку: `cd steps/04_middleware_redis`.

```bash
pip install -r requirements.txt
pytest                      # 41 тест: SQLite у пам'яті + fakeredis
mypy --strict news_hub      # перевірка типів

# база: без DATABASE_URL — файл news_hub.db (SQLite); з PostgreSQL:
docker compose up -d db redis
export DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub   # Windows: set DATABASE_URL=...
export REDIS_URL=redis://localhost:6379/0                                     # без Redis: REDIS_URL=fakeredis://

alembic upgrade head        # створити / оновити таблиці
uvicorn news_hub.api:app --reload
```

Ті самі тести на справжніх серверах: `TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test TEST_REDIS_URL=redis://localhost:6379/15 pytest` (базу `news_hub_test` створи заздалегідь; Redis-база 15 очищується перед кожним тестом).

- http://127.0.0.1:8000/docs — Swagger UI: спершу `POST /api/scrape` з `{"source": "snapshot"}`, потім `GET /api/news`;
- Postman: Import → `postman/news_hub.postman_collection.json` → Run collection;
- без Postman: `npx newman run postman/news_hub.postman_collection.json`.

Свіжа стрічка (коли `www.rbc.ua` доступний з мережі) — `POST /api/scrape` з `{}` або
`{"mode": "sequential"}`; у відповіді — час кожної сторінки й помилки, якщо сторінка не завантажилась.

## Порівняння з попереднім кроком

```bash
git diff --no-index --stat steps/03_sqlalchemy_alembic steps/04_middleware_redis
git diff --no-index steps/03_sqlalchemy_alembic/news_hub steps/04_middleware_redis/news_hub
```

## Що далі

[Крок 5. Тестування API](../05_api_testing/index.md)
