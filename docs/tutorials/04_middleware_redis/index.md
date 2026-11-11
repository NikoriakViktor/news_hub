# Крок 4. Middleware, кеш і Redis

> **Код кроку:** [`steps/04_middleware_redis`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/04_middleware_redis).
>
> **Передумови:** [Крок 3. База даних: SQLAlchemy і Alembic](../03_sqlalchemy_alembic/index.md) — новини в базі, `NewsRepository`, `get_db` робить COMMIT до відповіді.

## Де ми зараз { #where }

Після кроку 3 агрегатор зберігає новини в базі: `NewsRepository` виконує весь SQL, унікальний `url` гарантує база, `GET/POST/PATCH/DELETE /api/news…` — повний CRUD, а `Depends(get_db, scope="function")` робить COMMIT **до** відповіді клієнту.

Це вже справжній сервіс. А в живого сервісу з'являються проблеми, яких не видно, поки ним користуєшся сам.

## Проблема { #problem }

- **Кожен `GET /api/news` — запит до бази**, навіть якщо стрічка не змінювалась годину. Стрічку й статистику читають сотні разів, а змінюються вони лише під час збору.
- **`POST /api/scrape` можна смикати без обмежень.** Кожен живий збір — сім сторінок rbc.ua (крок 2). Скрипт у циклі навантажить і наш сервер, і чужий сайт.
- **Збір триває секунди, а клієнт увесь цей час чекає.** Сім сторінок з тайм-аутом 15 с кожна: клієнт може відвалитись за тайм-аутом, проксі — обірвати з'єднання.
- **У журналі нема за що вхопитись.** Коли щось піде не так, не видно, який саме запит це був і скільки він тривав.

## Що додаємо { #what }

| Що | Де | Розділ |
|---|---|---|
| код навколо кожного запиту: `X-Request-ID`, `X-Process-Time`, рядок журналу; порядок шарів | `news_hub/middleware.py`, `api.py` | [Middleware](middleware.md) |
| кеш `GET /api/news` і `/api/news/stats` у Redis (cache-aside), `X-Cache: HIT/MISS`, версія кешу | `news_hub/cache.py`, `api.py`, `middleware.py` | [Кеш стрічки в Redis](cache.md) |
| не більше 5 `POST /api/scrape*` за 60 с з однієї адреси: `429`, `Retry-After`, `X-RateLimit-*` | `news_hub/middleware.py` | [Rate limit: `429` і `Retry-After`](rate_limit.md) |
| `POST /api/scrape/jobs` → `202` + `job_id`, статус — `GET /api/scrape/jobs/{job_id}` | `news_hub/jobs.py`, `api.py` | [Фоновий збір: `202` і статус задачі](background_jobs.md) |

Redis — новий сервіс поруч із базою: сервер, що тримає ключі зі значеннями в пам'яті й сам видаляє ключ, коли минає його час життя (TTL). Для розробки — `docker compose up -d redis`, для тестів — `fakeredis` у пам'яті процесу.

## Архітектура: було → стало { #architecture }

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph OLD ["крок 3: база"]
        direction LR
        C0["клієнт"] --> A0["ендпоінт"] --> R0["NewsRepository"] --> D0[("база<br>SQLite / PostgreSQL")]
        A0 -.-> S0["збір 7 сторінок<br>клієнт чекає"]
    end
    subgraph NEW ["крок 4: middleware і Redis"]
        direction LR
        C1["клієнт"] --> MW["middleware<br>id, час, 429, версія кешу"]
        MW --> A1["ендпоінт"]
        A1 -- "hit" --> K[("Redis<br>кеш, ліміти, задачі")]
        A1 -- "miss" --> R1["NewsRepository"] --> D1[("база")]
        A1 -- "202" --> BG["BackgroundTasks<br>run_scrape_job"]
        BG --> R1
        BG --> K
    end
    OLD --> NEW

    class C0,A0,R0,C1,A1,R1 step
    class S0 error
    class D0,D1 success
    class MW,BG warning
    class K decision
```

- **Middleware — наскрізне.** Журнал, час, ліміт, інвалідація кешу стосуються всіх ендпоінтів, тому їх не копіюють у кожен.
- **Redis — не основне сховище.** Кеш, лічильники лімітів, статуси задач можна втратити без шкоди: кеш перерахується, ліміт почнеться з нуля, статус задачі — лише для зручності. Новини — тільки в базі.
- **Порядок подій важливий.** Інвалідація кешу — після COMMIT; фонова задача — після відповіді й зі своєю сесією бази.
- **Адреса клієнта.** Ліміт рахується за `request.client.host` — адресою того, хто підключився. За проксі це адреса проксі, і всі клієнти ділитимуть один ліміт. Як nginx передає справжню адресу і кому можна вірити — [крок 11](../11_compose_deploy/index.md).

## Файли кроку { #files }

| Файл | Що в ньому | Новий? |
|---|---|---|
| [`news_hub/cache.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/news_hub/cache.py) | `make_redis` (`REDIS_URL`, `fakeredis://`), `get_redis`, `NewsCache` — cache-aside з версією | новий |
| [`news_hub/middleware.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/news_hub/middleware.py) | `request_context`, `RateLimiter` + `rate_limit`, `invalidate_cache` | новий |
| [`news_hub/jobs.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/news_hub/jobs.py) | `JobStatus`, `JobStore` (hash `job:<id>` у Redis), `run_scrape_job` | новий |
| [`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/news_hub/api.py) | Redis у `lifespan`, реєстрація middleware, кеш у `list_news` і `news_stats`, `collect`, `POST /api/scrape/jobs`, `GET /api/scrape/jobs/{job_id}`, журнал | змінений |
| [`tests/test_redis.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/tests/test_redis.py) | 9 тестів: кеш, інвалідація, заголовки, `429`, фоновий збір | новий |
| [`tests/conftest.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/tests/conftest.py) | `REDIS_URL` → `fakeredis://` (або `TEST_REDIS_URL`), чистий Redis на кожен тест, тестова база й для фонових задач | змінений |
| [`docker-compose.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/docker-compose.yml) | + сервіс `redis` (`redis:7-alpine`, порт 6379) | змінений |
| [`requirements.txt`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/requirements.txt) | + `redis>=5.0.1`, `fakeredis>=2.26` | змінений |
| [`postman/news_hub.postman_collection.json`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/postman/news_hub.postman_collection.json) | 16 запитів, 25 перевірок (було 13 і 20): кеш, заголовки, фоновий збір з опитуванням статусу | змінений |
| `news_hub/db.py`, `tables.py`, `repository.py`, `models.py`, `parser.py`, `scraper.py`, `snapshot.py`, `migrations/` | з кроку 3 | без змін |

## Порядок читання { #reading-order }

1. [Middleware: код навколо кожного запиту](middleware.md) — `call_next`, порядок шарів, `X-Request-ID`.
2. [Кеш стрічки в Redis](cache.md) — cache-aside, ключ з параметрів, версія кешу і чому її збільшують після COMMIT.
3. [Rate limit: `429` і `Retry-After`](rate_limit.md) — `INCR` + `EXPIRE … NX` однією транзакцією, межа фіксованого вікна.
4. [Фоновий збір: `202` і статус задачі](background_jobs.md) — `BackgroundTasks`, статус у Redis, своя сесія бази.
5. [Контрольна точка](checkpoint.md) — тести, практика, самоперевірка.

Теорія до кроку — [Частина VI. Middleware, кеш і фонові задачі](../../06_middleware_cache_jobs/README.md); ще один стандартний middleware — [CORS](../../06_middleware_cache_jobs/cors.md).

## Запуск { #run }

З папки кроку `steps/04_middleware_redis`:

```bash
pip install -r requirements.txt
pytest -q                           # 41 passed: SQLite у пам'яті + fakeredis
mypy --strict news_hub              # Success: no issues found in 12 source files

docker compose up -d redis          # Redis 7 на localhost:6379 (db — PostgreSQL з кроку 3, якщо потрібен)
export REDIS_URL=redis://localhost:6379/0     # Windows: set REDIS_URL=...; без сервера: REDIS_URL=fakeredis://
alembic upgrade head
uvicorn news_hub.api:app --reload   # → http://127.0.0.1:8000/docs
```

Без `REDIS_URL` застосунок підключається до `redis://localhost:6379/0`. `fakeredis://` тримає дані в пам'яті процесу: кеш і ліміти працюють, але зникають з перезапуском і не спільні між процесами — це для тестів і пробних запусків, не для сервера.

Ті самі тести на справжніх серверах (Redis-база 15 очищується перед кожним тестом; базу `news_hub_test` створи заздалегідь):

```bash
TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test \
TEST_REDIS_URL=redis://localhost:6379/15 pytest
```

На справжньому Redis 7 (`TEST_REDIS_URL`, база — SQLite у пам'яті) результат той самий: `41 passed`.

## Порівняння з кроком 3 { #diff }

```bash
git diff --no-index --stat steps/03_sqlalchemy_alembic steps/04_middleware_redis
git diff --no-index steps/03_sqlalchemy_alembic/news_hub steps/04_middleware_redis/news_hub
```

Три нові модулі (`cache.py`, `jobs.py`, `middleware.py`) і зміни в `api.py`. Репозиторій, таблиці й міграції не змінились: Redis з'явився **поруч** із базою, а не замість неї.

## Що далі { #next }

[Крок 5. Тестування API](../05_api_testing/index.md): тести розділяться на unit та integration, мережу підмінять мок і фейковий сервер, API перевірятимуть асинхронно через `httpx` — зокрема 10 одночасних `POST /api/scrape`, які мають упертися рівно в ліміт.
