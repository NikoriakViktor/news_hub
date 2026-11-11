# news_hub — новинний агрегатор (крок 5: тести)

Наскрізний проєкт книги: парсер новин → перевірені моделі → API → база → кеш → підсумки від Gemini → Telegram-бот → Docker. Кожен крок — рефакторинг проєкту попереднього.

| Крок | Що додається |
|---|---|
| 1 | стартовий парсер з анотаціями типів; `NewsItem` на Pydantic |
| 2 | FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman |
| 3 | SQLAlchemy: новини в базі, унікальний `url`, повний CRUD, Alembic |
| 4 | middleware, кеш і rate limit на Redis, фоновий збір |
| **5** | **тести: unit / integration, HTML-фікстури, мок і фейк мережі, httpx, покриття** ← ти тут |
| 6 | Claude Code у проєкті: CLAUDE.md, дозволи, hook; друге джерело — RSS «Української правди», написане AI за тестами |
| 7 | LLM: підсумок, тема, тональність, ключові слова — Gemini (або Anthropic) за спільним інтерфейсом, перевірка Pydantic, кеш, circuit breaker |
| 8 | безпека: запис лише адміну з JWT, RSS-джерела за URL без SSRF, підписані webhook |
| 9 | Telegram-бот: `/news`, `/digest`, підписки на слова й сповіщення, webhook у FastAPI |
| 10 | Docker: образ застосунку — `Dockerfile`, `.dockerignore`, користувач без root, HEALTHCHECK, `/health/ready` |
| 11 | Compose: nginx → api → PostgreSQL + Redis, міграції окремим кроком, бот; реальний IP клієнта за nginx; бекап |
| 12 | CI/CD: GitHub Actions на кожен PR — тести ×2 Python, мінімальні версії, PostgreSQL, mypy, образ + smoke; образ у ghcr.io з main |

## Що тут

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
├── pytest.ini        ← крок 5: маркери unit / integration, asyncio
├── .coveragerc       ← крок 5: покриття гілок, concurrency = thread,greenlet (async SQLAlchemy)
└── tests/
    ├── conftest.py   ← фікстура html("…"), маркер за папкою
    ├── factories.py  ← make_raw(**зміни) — тестова новина
    ├── fixtures/     ← збережені сторінки: справжній фрагмент rbc.ua і демо-розмітка
    ├── unit/         ← парсер, модель, конвеєр, скрапер під моком (без бази й мережі)
    └── integration/  ← API (TestClient і httpx.AsyncClient), CRUD, Redis, справжній get_db,
                        скрапер проти локального aiohttp-сервера
```

## Запуск

```bash
pip install -r requirements.txt
pytest                      # 86 тестів: SQLite у пам'яті + fakeredis + локальний aiohttp-сервер
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

Розбір змін — [Крок 5 у книзі](https://nikoriakviktor.github.io/news_hub/tutorials/05_api_testing/).
