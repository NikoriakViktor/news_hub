# Крок 3. База даних: SQLAlchemy і Alembic

> **Код кроку:** [`steps/03_sqlalchemy_alembic`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/03_sqlalchemy_alembic).
>
> **Передумови:** [Крок 2. Перший API на FastAPI](../02_fastapi_basics/index.md) — є FastAPI-застосунок і сховище `NewsStore` через `Depends`.

## Де ми зараз { #where }

Після кроку 2 агрегатор — HTTP-сервіс: `POST /api/scrape` збирає новини, `GET /api/news` віддає їх з фільтрами, `/docs` описує API. Ендпоінти отримують сховище через `Depends(get_store)` і не знають, як воно влаштоване.

А влаштоване воно просто: `NewsStore` — словник `url → NewsItem` у пам'яті процесу uvicorn.

## Проблема { #problem }

Словник у пам'яті не годиться для справжнього сервісу:

- **зупинили сервер — новин немає.** Кожен перезапуск (оновлення коду, `--reload`, падіння) починає з порожнього сховища;
- **два процеси — два різні сховища.** Запустиш два uvicorn — кожен бачитиме лише свої новини;
- **унікальність `url` тримає лише наш код.** Будь-яка інша програма, що пише дані, про це правило не знає;
- **немає окремої новини.** Знайти, змінити чи видалити одну новину API не вміє: у неї немає ідентифікатора.

Потрібна **база даних**: дані живуть поза процесом, правила (`UNIQUE`, `NOT NULL`) перевіряє сама база, кожен рядок має `id`. І ще потрібен спосіб змінювати схему бази разом із кодом, не втрачаючи вже зібраних новин.

## Що додаємо { #what }

| Що | Де | Розділ |
|---|---|---|
| engine, фабрика сесій, таблиця `news` як клас `NewsRow` | `news_hub/db.py`, `tables.py` | [Engine, сесії й таблиця](engine_and_table.md) |
| `NewsRepository` — той самий контракт, що `NewsStore`, але SQL | `news_hub/repository.py` | [Репозиторій замість `NewsStore`](repository.md) |
| `get_db`: одна сесія й транзакція на запит, COMMIT до відповіді | `news_hub/db.py`, `api.py` | [Сесія на запит і COMMIT до відповіді](session_per_request.md) |
| `POST /api/news`, `GET/PATCH/DELETE /api/news/{news_id}`, пошук; `201/404/409/204` | `news_hub/api.py` | [Повний CRUD](crud.md) |
| міграції схеми, PostgreSQL у Docker | `migrations/`, `alembic.ini`, `docker-compose.yml` | [Міграції Alembic](alembic.md) |

## Архітектура: було → стало { #architecture }

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph OLD ["крок 2: у пам'яті процесу"]
        direction LR
        A0["api.py"] -- "Depends" --> S0["NewsStore<br>dict url → NewsItem"]
        S0 --> L0["зникає при<br>перезапуску"]
    end
    subgraph NEW ["крок 3: база даних"]
        direction LR
        A1["api.py<br>CRUD, 201/404/409/204"] -- "Depends" --> R1["NewsRepository<br>увесь SQL"]
        A1 -- "Depends, scope=function" --> G1["get_db<br>сесія й транзакція"]
        R1 --> G1
        G1 --> DB[("PostgreSQL<br>або SQLite")]
        M1["Alembic<br>migrations/"] --> DB
        T1["tables.py<br>NewsRow"] -.-> R1
        T1 -.-> M1
    end
    subgraph NEXT ["далі"]
        direction LR
        N1["крок 4: кеш Redis<br>перед репозиторієм"] ~~~ N2["крок 5: тести API<br>на тестовій базі"] ~~~ N3["крок 7: стовпці LLM<br>міграція 0002"]
    end
    OLD --> NEW --> NEXT

    class A0,S0 step
    class L0 error
    class A1,R1,T1 step
    class G1 warning
    class DB,M1 success
    class N1,N2,N3 success
```

- **Репозиторій — єдине місце з SQL.** Ендпоінти не знають, PostgreSQL під ними чи SQLite. Ті самі 32 тести проходять на обох базах (`TEST_DATABASE_URL`).
- **Транзакція = запит.** `get_db` відкриває сесію, ендпоінт працює, COMMIT — до відповіді (`scope="function"`). Той самий принцип для кількох репозиторіїв називають Unit of Work — [Частина V](../../05_databases/README.md).
- **Правила даних — у базі.** `UNIQUE (url)` тримає і API, і міграції, і будь-яку іншу програму, що пише в `news`. Код лише перетворює порушення на зрозумілий `409`.
- **Схема — у git.** `tables.py` описує, якою таблиця має бути; `migrations/` — як до цього дійти з будь-якої попередньої версії.

## Файли кроку { #files }

| Файл | Що в ньому | Новий? |
|---|---|---|
| [`news_hub/db.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/news_hub/db.py) | `DATABASE_URL`, `make_engine`, `SessionFactory`, `Base`, `get_db` | новий |
| [`news_hub/tables.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/news_hub/tables.py) | `NewsRow` — таблиця `news` (SQLAlchemy 2.0) | новий |
| [`news_hub/repository.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/news_hub/repository.py) | `BaseRepository`, `NewsRepository`: `add_many`, `create`, `find`, `search`, `stats`, `clear` | новий |
| [`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/news_hub/api.py) | `SessionDep`, `RepoDep`, `RowDep`, `NewsOut`, `NewsCreate`, `NewsPatch`; 11 операцій | змінено |
| `news_hub/store.py` | `NewsStore` з кроку 2 | видалено |
| [`migrations/versions/0001_news_table.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/migrations/versions/0001_news_table.py) | перша міграція: таблиця `news` і три індекси | новий |
| [`migrations/env.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/migrations/env.py), [`alembic.ini`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/alembic.ini) | async-міграції; адреса бази — з `news_hub.db` | новий |
| [`docker-compose.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/docker-compose.yml) | PostgreSQL 16 для розробки | новий |
| [`tests/conftest.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/tests/conftest.py) | фікстура `client`: окремий engine і порожні таблиці на кожен тест | новий |
| [`tests/test_crud.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/tests/test_crud.py) | 9 тестів CRUD | новий |
| [`tests/test_api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/tests/test_api.py) | 11 тестів API; фікстура переїхала в `conftest.py` | змінено |
| [`postman/news_hub.postman_collection.json`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/postman/news_hub.postman_collection.json) | 13 запитів (було 7): додано CRUD | змінено |
| [`requirements.txt`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/requirements.txt) | `sqlalchemy[asyncio]`, `asyncpg`, `aiosqlite`, `alembic`; `fastapi>=0.121` | змінено |
| `news_hub/models.py`, `parser.py`, `snapshot.py`, `scraper.py` | з кроків 1–2 | без змін |

Структура після кроку:

```text
news_hub/
├── news_hub/
│   ├── parser.py     ← parse_rbc_news + типи: HTML → list[RawNews]
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

## Порядок читання { #reading-order }

1. [Engine, сесії й таблиця](engine_and_table.md) — підключення до бази й таблиця як клас.
2. [Репозиторій замість `NewsStore`](repository.md) — ті самі методи, але SQL; `ON CONFLICT` і дірки в `id`.
3. [Сесія на запит і COMMIT до відповіді](session_per_request.md) — `get_db`, `flush`, `scope="function"`.
4. [Повний CRUD](crud.md) — `201`, `404`, `409`, `204`, `PATCH` лише переданих полів.
5. [Міграції Alembic](alembic.md) — схема бази як код.
6. [Контрольна точка](checkpoint.md) — тести, практика, самоперевірка.

Теорія до кроку — [Частина V. Бази даних: SQLAlchemy async і Alembic](../../05_databases/README.md) і [Залежності: коли виконується код після `yield`](../../03_fastapi_core/dependencies.md#yield-timing).

## Запуск { #run }

З папки кроку `steps/03_sqlalchemy_alembic`:

```bash
pip install -r requirements.txt
pytest -q                           # 32 passed (SQLite у пам'яті)
mypy --strict news_hub              # Success: no issues found in 9 source files

# база: без DATABASE_URL — файл news_hub.db (SQLite) поруч із проєктом; з PostgreSQL:
docker compose up -d db
export DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub   # Windows: set DATABASE_URL=...

alembic upgrade head                # створити / оновити таблиці
uvicorn news_hub.api:app --reload   # → http://127.0.0.1:8000/docs
```

Ті самі тести на PostgreSQL (базу `news_hub_test` створи заздалегідь):

```bash
TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test pytest -q   # 32 passed
```

- `/docs`: спершу `POST /api/scrape` з `{"source": "snapshot"}`, потім `GET /api/news`;
- Postman: Import → `postman/news_hub.postman_collection.json` → Run collection;
- без Postman: `npx newman run postman/news_hub.postman_collection.json`.

!!! warning "Спершу `alembic upgrade head`"
    `lifespan` у кроці 3 таблиць **не створює** — це робота міграцій. Без `alembic upgrade head` сервер стартує і `/health` відповідає, але `GET /api/news` повертає `500`, а в журналі uvicorn — `sqlite3.OperationalError: no such table: news`.

## Порівняння з кроком 2 { #diff }

```bash
git diff --no-index --stat steps/02_fastapi_basics steps/03_sqlalchemy_alembic
git diff --no-index steps/02_fastapi_basics/news_hub steps/03_sqlalchemy_alembic/news_hub
```

## Що далі { #next }

[Крок 4. Middleware, кеш і Redis](../04_middleware_redis/index.md): кожен `GET /api/news` тепер — SQL-запит. Крок 4 поставить перед репозиторієм кеш у Redis, обмежить частоту запитів і винесе збір у фон.
