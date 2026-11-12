# Бази даних: SQL, SQLAlchemy async, транзакції, Repository, пул, Alembic

Python 3.11+.

```bash
pip install -r requirements.txt
```

Без `DATABASE_URL` усі Python-скрипти працюють із файлом SQLite у тимчасовій папці — у репозиторії нічого не лишається.
Частина розділів (конкурентні оновлення, рівні ізоляції, пул, `EXPLAIN`) має сенс лише на PostgreSQL:

```bash
docker run --rm -d --name part05-pg -p 5544:5432 -e POSTGRES_PASSWORD=x postgres:16-alpine
export DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres
# … скрипти …
docker stop part05-pg          # --rm: контейнер і дані зникнуть
```

| Файл | Що показує | База |
|---|---|---|
| `sql/sql_basics.sql` | ключі, обмеження, `SELECT`, `GROUP BY`, `JOIN`, підзапити, транзакції | PostgreSQL: `docker exec -i part05-pg psql -U postgres < sql/sql_basics.sql` |
| `sql/indexes.sql` | `EXPLAIN`, індекси для API (після `sql_basics.sql`) | PostgreSQL |
| `sqlalchemy_demo.py` | Core і ORM, identity map, ліниві зв'язки в async, N+1, `selectinload`/`joinedload` | обидві |
| `n_plus_one.py` | N+1 на 500 джерелах: запити й час | обидві |
| `injection_demo.py` | f-рядок у `text()`, параметри, білий список сортування, `%` у `LIKE` | обидві |
| `transactions_demo.py` | все або нічого, `PendingRollbackError`, `expire_on_commit`, `SAVEPOINT`, `ON CONFLICT`, втрачене оновлення, ізоляція | обидві; розділ 7 — PostgreSQL |
| `uow_demo.py` | Unit of Work, фейки з семантикою транзакції й без неї, `SAVEPOINT` у SQLite | обидві |
| `news_app/` + `tests/` | Repository + Unit of Work + FastAPI; контрактні тести фейка й SQL-реалізації | `pytest -q`; `TEST_DATABASE_URL=…` — PostgreSQL |
| `pool_demo.py` | пул: ціна з'єднання, черга, тайм-аути, `pool_pre_ping`, з'єднання на воркери, asyncpg напряму | PostgreSQL |
| `asyncpg_app.py` | FastAPI з пулом asyncpg без SQLAlchemy: пул у `lifespan`, з'єднання через `Depends` | PostgreSQL |
| `migrations_demo.py` + `migrations_demo/` | Alembic: expand/contract з даними, autogenerate, `alembic check`, дві голови, `lock_timeout` | обидві; на PostgreSQL — окрема база |

```bash
python sqlalchemy_demo.py
pytest -q
TEST_DATABASE_URL=$DATABASE_URL pytest -q
docker exec part05-pg createdb -U postgres migrations
DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/migrations python migrations_demo.py
DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/migrations alembic -c migrations_demo/alembic.ini upgrade head --sql
```

Розбір — Частина V книги «Бази даних: SQLAlchemy async і Alembic».
