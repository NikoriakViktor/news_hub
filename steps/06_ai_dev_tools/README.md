# news_hub — новинний агрегатор (крок 6: AI-асистент у проєкті)

Наскрізний проєкт FastAPI-гілки курсу: парсер новин → перевірені моделі → API → база → кеш → підсумки від Gemini → Telegram-бот → Docker. Кожен урок — рефакторинг проєкту попереднього.

| Урок | Крок |
|---|---|
| 37 | стартовий парсер з анотаціями типів; `NewsItem` на Pydantic |
| 38 | FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman |
| 39 | SQLAlchemy: новини в базі, унікальний `url`, повний CRUD, Alembic |
| 40 | middleware, кеш і rate limit на Redis, фоновий збір |
| 42 | тести: unit / integration, HTML-фікстури, мок і фейк мережі, httpx, покриття |
| **43** | **Claude Code у проєкті: CLAUDE.md, дозволи, hook; друге джерело — RSS «Української правди», написане AI за тестами** ← ти тут |
| 44 | Gemini: підсумок, категорія, тональність |
| 48 | Telegram-бот: `/news`, `/digest` |
| 48–50 | Docker, Compose, CI/CD |

## Що тут

```
news_hub/
├── news_hub/
│   ├── parser.py     ← стартовий parse_rbc_news + типи: HTML → list[RawNews]
│   ├── rss.py        ← урок 43: parse_pravda_rss — RSS «Української правди» → list[RawNews] (написав Claude Code)
│   ├── models.py     ← NewsItem (Pydantic), validate_news, is_allowed_host (rbc.ua, pravda.com.ua, epravda.com.ua)
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
├── CLAUDE.md         ← урок 43: інструкції для AI-асистента — команди, структура, правила проєкту
├── .claude/          ← урок 43: settings.json (дозволи), hooks/unit_tests.py (pytest -m unit після правок),
│                       skills/add-news-source/ (/add-news-source)
├── pytest.ini        ← урок 42: маркери unit / integration, asyncio
├── .coveragerc       ← урок 42: покриття гілок, concurrency = thread,greenlet (async SQLAlchemy)
└── tests/
    ├── conftest.py   ← фікстура html("…"), маркер за папкою
    ├── factories.py  ← make_raw(**зміни) — тестова новина
    ├── fixtures/     ← збережені сторінки: справжній фрагмент rbc.ua, демо-розмітка, pravda_rss.xml (навчальний знімок RSS)
    ├── unit/         ← парсер, модель, конвеєр, скрапер під моком; test_pravda.py — специфікація для AI,
    │                   test_pravda_review.py — що знайшла рецензія його коду
    └── integration/  ← API (TestClient і httpx.AsyncClient), CRUD, Redis, справжній get_db,
                        скрапер проти локального aiohttp-сервера
```

Джерела коду: Redis-клієнт — `production_bot/backend/core/redis.py`, rate limit — `ai_bot/app/middlewares/rate_limit.py` і `repositories/rate_limit_repo.py`, фоновий збір — `/api/scrape/archive` з `news_dashboard`; база й репозиторій — стартовий `production_bot/backend/core/database.py`, `repositories/base.py`, `migrations/`; API і скрапер — прототип `news_dashboard/app/main.py` і `scraper.py`; `parse_rbc_news` — ноутбук про веб-скрапінг `note_lesson_32_web_scraping.ipynb`; словник категорій — `news_dashboard/app/scraper.py`. Знімок — `rbc_news.json` поруч із тим самим ноутбуком.

## Запуск

```bash
pip install -r requirements.txt
pytest                      # 107 тестів: SQLite у пам'яті + fakeredis + локальний aiohttp-сервер
pytest -m unit              # лише швидкі, без бази, Redis і мережі
pytest --cov=news_hub       # покриття (налаштування — .coveragerc)
mypy --strict news_hub      # перевірка типів

# база: без DATABASE_URL — файл news_hub.db (SQLite); з PostgreSQL:
docker compose up -d db redis
export DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub   # Windows: set DATABASE_URL=...
export REDIS_URL=redis://localhost:6379/0                                     # без Redis: REDIS_URL=fakeredis://

alembic upgrade head        # створити / оновити таблиці
uvicorn news_hub.api:app --reload
```

Ті самі тести на справжніх серверах: `TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test TEST_REDIS_URL=redis://localhost:6379/15 pytest` (базу `news_hub_test` створи заздалегідь; Redis-база 15 очищується перед кожним тестом). Лише так ловиться гонка в rate limit: fakeredis не віддає керування циклу подій, тож одночасних запитів на ньому не буває (`tests/integration/test_async_api.py`).

- http://127.0.0.1:8000/docs — Swagger UI: спершу `POST /api/scrape` з `{"source": "snapshot"}`, потім `GET /api/news`;
- Postman: Import → `postman/news_hub.postman_collection.json` → Run collection;
- без Postman: `npx newman run postman/news_hub.postman_collection.json`.

Свіжа стрічка (коли `www.rbc.ua` доступний з мережі) — `POST /api/scrape` з `{}` або
`{"mode": "sequential"}`; у відповіді — час кожної сторінки й помилки, якщо сторінка не завантажилась.

Урок 43: `rss.py` і зміни в `models.py` написав Claude Code (`claude -p`) за специфікацією `tests/unit/test_pravda.py`.
Рецензія його коду — `tests/unit/test_pravda_review.py`.

Розбір змін — [Крок 6 у книзі](https://nikoriakviktor.github.io/news_hub/tutorials/06_ai_dev_tools/) · урок 43 курсу.
