# news_hub — новинний агрегатор (крок 3: база даних)

Наскрізний проєкт книги: парсер новин → перевірені моделі → API → база → кеш → підсумки від Gemini → Telegram-бот → Docker. Кожен крок — рефакторинг проєкту попереднього.

| Крок | Що додається |
|---|---|
| 1 | стартовий парсер з анотаціями типів; `NewsItem` на Pydantic |
| 2 | FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman |
| **3** | **SQLAlchemy: новини в базі, унікальний `url`, повний CRUD, Alembic** ← ти тут |
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
│   ├── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
│   ├── scraper.py    ← крок 2: сторінки rbc.ua через aiohttp — разом (gather) або по черзі
│   ├── db.py         ← крок 3: engine, сесії, get_db (сесія й транзакція на запит)
│   ├── tables.py     ← крок 3: NewsRow — таблиця news (SQLAlchemy 2.0)
│   ├── repository.py ← крок 3: NewsRepository — увесь SQL; замінив NewsStore з кроку 2
│   └── api.py        ← FastAPI: /api/news (+ CRUD /api/news/{id}), /stats, POST /api/scrape
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── migrations/       ← крок 3: Alembic — версії схеми бази (0001: таблиця news)
├── alembic.ini
├── docker-compose.yml ← крок 3: PostgreSQL 16 для розробки
├── postman/news_hub.postman_collection.json   ← 13 запитів з перевірками
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
└── tests/            ← pytest: моделі, парсер, знімок, API і CRUD (TestClient; SQLite або PostgreSQL)
```

## Запуск

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

Розбір змін — [Крок 3 у книзі](https://nikoriakviktor.github.io/news_hub/tutorials/03_sqlalchemy_alembic/).
