# news_hub — новинний агрегатор (крок 4: Redis і middleware)

Наскрізний проєкт FastAPI-гілки курсу: парсер новин → перевірені моделі → API → база → кеш → підсумки від Gemini → Telegram-бот → Docker. Кожен урок — рефакторинг проєкту попереднього.

| Урок | Крок |
|---|---|
| 37 | стартовий парсер з анотаціями типів; `NewsItem` на Pydantic |
| 38 | FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman |
| 39 | SQLAlchemy: новини в базі, унікальний `url`, повний CRUD, Alembic |
| **40** | **middleware, кеш і rate limit на Redis, фоновий збір** ← ти тут |
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
│   ├── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
│   ├── scraper.py    ← урок 38: сторінки rbc.ua через aiohttp — разом (gather) або по черзі
│   ├── db.py         ← урок 39: engine, сесії, get_db (сесія й транзакція на запит)
│   ├── tables.py     ← урок 39: NewsRow — таблиця news (SQLAlchemy 2.0)
│   ├── repository.py ← урок 39: NewsRepository — увесь SQL; замінив NewsStore з уроку 38
│   ├── cache.py      ← урок 40: клієнт Redis, NewsCache (cache-aside з версією)
│   ├── middleware.py ← урок 40: X-Request-ID / X-Process-Time, rate limit → 429, інвалідація кешу
│   ├── jobs.py       ← урок 40: фоновий збір, статус задачі в Redis
│   └── api.py        ← FastAPI: /api/news (+ CRUD, кеш), /stats, POST /api/scrape, /api/scrape/jobs
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── migrations/       ← урок 39: Alembic — версії схеми бази (0001: таблиця news)
├── alembic.ini
├── docker-compose.yml ← PostgreSQL 16 (урок 39) і Redis 7 (урок 40) для розробки
├── postman/news_hub.postman_collection.json   ← 16 запитів з перевірками
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
└── tests/            ← pytest: моделі, парсер, API, CRUD, Redis (TestClient; SQLite/PostgreSQL, fakeredis/Redis)
```

Джерела коду: Redis-клієнт — `production_bot/backend/core/redis.py`, rate limit — `ai_bot/app/middlewares/rate_limit.py` і `repositories/rate_limit_repo.py`, фоновий збір — `/api/scrape/archive` з `news_dashboard`; база й репозиторій — стартовий `production_bot/backend/core/database.py`, `repositories/base.py`, `migrations/`; API і скрапер — прототип `news_dashboard/app/main.py` і `scraper.py`; `parse_rbc_news` — ноутбук про веб-скрапінг `note_lesson_32_web_scraping.ipynb`; словник категорій — `news_dashboard/app/scraper.py`. Знімок — `rbc_news.json` поруч із тим самим ноутбуком.

## Запуск

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

Розбір змін — [урок 40 у книзі курсу](https://nikoriakviktor.github.io/PY-Course-Victor-Nikoriak-11-11-2026/modules/m4/lesson_40/).
