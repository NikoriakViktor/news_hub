# Фінальна лаба. Пошуковий індекс { #final }

| | |
|---|---|
| Основа | [крок 12](../tutorials/12_ci_cd/index.md) — `steps/12_ci_cd` |
| Що тренує | план запиту (`EXPLAIN`), trigram-індекс `pg_trgm`, міграція без блокування таблиці, модель ↔ міграція ↔ `alembic check`, тест, який перевіряє план |
| Складність | ★★★ |
| Орієнтовний час | 4–6 год + захист |
| Готовий патч | [`news_hub_search_index.patch`](news_hub_search_index.patch) |

## Мета { #goal }

**Задача.** `GET /api/news/search?q=…` шукає підрядок у заголовку через
[`NewsRepository.search`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/news_hub/repository.py):
`NewsRow.title.icontains(q)`. На знімку зі 168 новин це миттєво. На 200 000 новин PostgreSQL щоразу
переглядає всю таблицю, бо `%` на початку шаблону робить звичайний B-tree марним.

**Зміна.** Міграція 0005 додає trigram-індекс (GIN з `gin_trgm_ops` розбиває рядок на трійки символів і шукає за ними)
і заодно прибирає індекс, який нічого не прискорює (`ix_subscriptions_chat_id`).

**Результат.** Той самий запит на 200 000 рядків — з 81 мс до 0.04 мс. Тести перевіряють модель, міграцію в обидва боки
й **план запиту** на PostgreSQL. Фінальна лаба відрізняється від решти саме цим: «працює» тут доводять виміром, а не
тим, що тести зелені.

**Правило.** Індекс будують під той вираз, який **справді** надсилає в базу код, а не під той, що видно в
`print(stmt)`.

## Звідки починаємо { #start }

Копія кроку 12 у корені репозиторію книжки:

```bash
cp -r steps/12_ci_cd lab_final
cd lab_final
pip install -r requirements-dev.txt
pytest -q                     # 363 passed, 8 deselected
mypy --strict news_hub        # Success: no issues found in 26 source files
```

Для плану запиту потрібен PostgreSQL. Найпростіше — сервіс `postgres` з Compose кроку
([крок 11](../tutorials/11_compose_deploy/index.md)):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres
export DATABASE_URL=postgresql+asyncpg://news:<POSTGRES_PASSWORD з .env>@localhost:5432/news_hub
export TEST_DATABASE_URL=postgresql+asyncpg://news:<POSTGRES_PASSWORD з .env>@localhost:5432/news_hub_test
```

База `news_hub_test` — окрема: тести роблять `drop_all` / `create_all`. Створи її один раз:
`docker compose exec postgres createdb -U news news_hub_test`.

## Частина 1. Виміряй, перш ніж лагодити { #measure }

Спершу — який SQL отримує PostgreSQL. Не `print(stmt)`: без діалекту SQLAlchemy друкує варіант «за замовчуванням».

```python
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite

from news_hub.tables import NewsRow

stmt = select(NewsRow.id).where(NewsRow.title.icontains("x", autoescape=True))
print(stmt)                                        # діалект за замовчуванням
print(stmt.compile(dialect=sqlite.dialect()))
print(stmt.compile(dialect=postgresql.dialect()))
```

```text
WHERE (lower(news.title) LIKE '%' || lower(:title_1) || '%' ESCAPE '/')
WHERE (lower(news.title) LIKE '%' || lower(?) || '%' ESCAPE '/')
WHERE (news.title ILIKE '%%' || %(title_1)s::VARCHAR || '%%' ESCAPE '/')
```

(показано лише рядок `WHERE`; SQLAlchemy 2.1.8, так само на найнижчій дозволеній 2.0.30). На PostgreSQL це
**`title ILIKE …`**, а не `lower(title) LIKE …` — докстрінг `search()` описує варіант SQLite.

Тепер план. Таблиця з 200 000 заголовків, запит, як у `search()`, слово, якого немає в жодному заголовку
(найгірший випадок — база мусить переконатися, що збігів немає), PostgreSQL 16:

```sql
EXPLAIN (ANALYZE, COSTS OFF)
SELECT id FROM bench WHERE title ILIKE '%кременчук%' ORDER BY id LIMIT 20;
```

```text
-- 1. без індексу
 ->  Parallel Seq Scan on bench (actual time=73.539..73.540 rows=0 loops=3)
       Filter: ((title)::text ~~* '%кременчук%'::text)
       Rows Removed by Filter: 66667
 Execution Time: 81.201 ms

-- 2. CREATE INDEX … USING gin (lower(title) gin_trgm_ops)
 ->  Parallel Seq Scan on bench (actual time=72.423..72.423 rows=0 loops=3)
       Filter: ((title)::text ~~* '%кременчук%'::text)
       Rows Removed by Filter: 66667
 Execution Time: 78.278 ms

-- 3. CREATE INDEX … USING gin (title gin_trgm_ops)
 ->  Bitmap Index Scan on bench_title_trgm (actual time=0.016..0.016 rows=0 loops=1)
       Index Cond: ((title)::text ~~* '%кременчук%'::text)
 Execution Time: 0.038 ms
```

Індекс 2 існує — і **не використовується**: запит питає про `title`, а індекс побудовано на виразі `lower(title)`.
Індекс 3 відповідає виразу запиту, і `pg_trgm` обслуговує не лише `LIKE`, а й `ILIKE` (`~~*`). Ціна: на цій таблиці
26 MB даних і ще 40 MB індексу.

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph S1["1 · код"]
        direction LR
        C1["NewsRow.title.icontains(q)"] --> C2["діалект postgresql"]
    end
    subgraph S2["2 · SQL у базі"]
        direction LR
        Q1["title ILIKE '%кременчук%'"]
    end
    subgraph S3["3 · планувальник"]
        direction LR
        D1{"індекс на<br>той самий вираз?"}
    end
    subgraph S4["4 · результат"]
        direction LR
        R1["gin (lower(title) …)<br>ні: Seq Scan, 78 мс"]
        R2["gin (title …)<br>так: Bitmap Index Scan, 0.04 мс"]
    end
    S1 --> S2 --> S3
    D1 -->|ні| R1
    D1 -->|так| R2

    class C1,C2,Q1 step
    class D1 decision
    class R1 error
    class R2 success
```

!!! warning "Частий випадок — не те саме, що рідкісний"
    Для слова, яке є в кожному п'ятому заголовку (`'%бюджет%'`), той самий запит з індексом 3 вибирає зовсім інший план:
    `Index Scan using bench_pkey` з фільтром, 0.229 ms — перші 20 збігів трапляються вже на початку перегляду за `id`, і
    база зупиняється. Індекс — ще один варіант для планувальника, а не наказ. Міряй і на рідкісних, і на частих
    значеннях.

## Вимоги { #requirements }

1. **Міграція `0005`** (`migrations/versions/0005_search_index.py`, `down_revision = "0004"`):
    - PostgreSQL: `CREATE EXTENSION IF NOT EXISTS pg_trgm`, потім
      `CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_title_trgm ON news USING gin (title gin_trgm_ops)`;
    - SQLite (тести й локальний запуск): звичайний індекс `ix_news_title_trgm` на `title` — trigram там немає, але схема
      має збігатися з моделлю;
    - прибрати `ix_subscriptions_chat_id`: його стовпець — початок `UNIQUE (chat_id, keyword)`, пошук за `chat_id` і так
      іде по унікальному індексу;
    - `downgrade()` повертає все як було (на PostgreSQL — `DROP INDEX CONCURRENTLY`).
2. **Модель** (`news_hub/tables.py`) знає про обидві зміни: `Index("ix_news_title_trgm", …)` у `NewsRow.__table_args__`,
   `SubscriptionRow.chat_id` без `index=True`.
3. **Тести на PostgreSQL** створюють схему через `create_all`, а не міграціями — `pg_trgm` має з'явитися і там.
4. `pytest -q` — зелений на SQLite і на PostgreSQL; `alembic upgrade head` → `alembic check` → `alembic downgrade -1` →
   `alembic upgrade head` → `alembic check` — без помилок на обох; `mypy --strict news_hub` — чистий.
5. Запис у [Частині 1](#measure) — твій: заміри на своїй машині й своїх даних, з номером версії PostgreSQL.

## Критерії приймання { #acceptance }

Поклади файл у `tests/integration/test_search_index.py`. Останній тест виконується лише з `TEST_DATABASE_URL` на
PostgreSQL: він перевіряє не наявність індексу, а те, що **умова з `search()`** його використовує.

```python title="tests/integration/test_search_index.py"
"""Фінальна лаба: індекс для пошуку за заголовком (міграція 0005).

Модель, міграція і план запиту — три місця, які мають збігатися. Тест плану запиту — лише на PostgreSQL:
    TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test pytest tests/integration/test_search_index.py
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Index, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from news_hub.db import Base, make_engine
from news_hub.tables import NewsRow, SubscriptionRow

PROJECT = Path(__file__).resolve().parents[2]
INDEX = "ix_news_title_trgm"
REDUNDANT = "ix_subscriptions_chat_id"
PG_URL = os.getenv("TEST_DATABASE_URL", "")


def indexes(model: type[Base]) -> dict[str, Index]:
    return {str(index.name): index for index in model.__table__.indexes}   # type: ignore[attr-defined]


def test_model_declares_trigram_index_on_title() -> None:
    index = indexes(NewsRow).get(INDEX)
    assert index is not None, f"NewsRow не оголошує {INDEX} — alembic check на PostgreSQL впаде"
    ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "USING gin (title gin_trgm_ops)" in ddl                     # search() на PostgreSQL — title ILIKE …


def test_subscriptions_have_no_redundant_chat_id_index() -> None:
    assert REDUNDANT not in indexes(SubscriptionRow)


def alembic(db: Path, *args: str) -> None:
    env = os.environ | {"DATABASE_URL": f"sqlite+aiosqlite:///{db}"}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=PROJECT, env=env,
                   capture_output=True, text=True, check=True)


def sqlite_indexes(db: Path) -> set[str]:
    with sqlite3.connect(db) as conn:
        return {name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}


def test_migration_0005_upgrade_and_downgrade(tmp_path: Path) -> None:
    db = tmp_path / "news_hub.db"
    alembic(db, "upgrade", "head")
    after_upgrade = sqlite_indexes(db)
    alembic(db, "downgrade", "-1")
    after_downgrade = sqlite_indexes(db)
    assert INDEX in after_upgrade and REDUNDANT not in after_upgrade
    assert INDEX not in after_downgrade and REDUNDANT in after_downgrade


@pytest.mark.skipif(not PG_URL.startswith("postgresql"), reason="план запиту — лише на PostgreSQL (TEST_DATABASE_URL)")
@pytest.mark.asyncio
async def test_search_condition_uses_trigram_index() -> None:
    # та сама умова, що в NewsRepository.search; SQL — як його згенерує SQLAlchemy для PostgreSQL
    condition = NewsRow.title.icontains("кременчук", autoescape=True)
    engine = make_engine(PG_URL)
    sql = str(select(NewsRow.id).where(condition).compile(engine, compile_kwargs={"literal_binds": True}))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)                  # before_create → CREATE EXTENSION pg_trgm
        await conn.execute(text("SET LOCAL enable_seqscan = off"))      # порожня таблиця: інакше Seq Scan дешевший
        plan = "\n".join((await conn.execute(text(f"EXPLAIN {sql}"))).scalars())
    await engine.dispose()
    assert f"Bitmap Index Scan on {INDEX}" in plan, plan
```

`SET LOCAL enable_seqscan = off` — не обман: у порожній таблиці перегляд справді дешевший за будь-який індекс, і без цього
планувальник ніколи не покаже, чи **може** він узяти індекс. Чи **візьме** на живих даних — це заміри з Частини 1.

**До змін** (крок 12 як є, з `TEST_DATABASE_URL` на PostgreSQL 16):

```text
E       AssertionError: NewsRow не оголошує ix_news_title_trgm — alembic check на PostgreSQL впаде
E       AssertionError: assert 'ix_subscriptions_chat_id' not in {'ix_subscriptions_chat_id': Index('ix_subscriptions_chat_id', ...)}
E       AssertionError: assert ('ix_news_title_trgm' in {'ix_news_ai_category', 'ix_news_category', 'ix_news_lang', ...})
E       AssertionError: Seq Scan on news  (cost=10000000000.00..10000000010.38 rows=1 width=4)
E           Filter: ((title)::text ~~* '%кременчук%'::text)
FAILED tests/integration/test_search_index.py::test_model_declares_trigram_index_on_title
FAILED tests/integration/test_search_index.py::test_subscriptions_have_no_redundant_chat_id_index
FAILED tests/integration/test_search_index.py::test_migration_0005_upgrade_and_downgrade
FAILED tests/integration/test_search_index.py::test_search_condition_uses_trigram_index
4 failed in 2.00s
```

**Після змін:**

```text
$ pytest -q                                   # SQLite
366 passed, 1 skipped, 8 deselected in 26.36s
$ TEST_DATABASE_URL=postgresql+asyncpg://… pytest -q
367 passed, 8 deselected in 47.79s
$ mypy --strict news_hub
Success: no issues found in 26 source files
```

Міграції — на обох базах:

```text
$ alembic upgrade head && alembic check
INFO  [alembic.runtime.migration] Running upgrade 0004 -> 0005, Пошук за заголовком — trigram-індекс; прибрати зайвий індекс subscriptions.chat_id
No new upgrade operations detected.
$ alembic downgrade -1 && alembic upgrade head && alembic check
INFO  [alembic.runtime.migration] Running downgrade 0005 -> 0004, …
INFO  [alembic.runtime.migration] Running upgrade 0004 -> 0005, …
No new upgrade operations detected.
```

```text
$ docker compose exec postgres psql -U news -d news_hub -c '\d news' | grep trgm
    "ix_news_title_trgm" gin (title gin_trgm_ops)
```

## Підказки { #hints }

??? tip "Чому `CONCURRENTLY` і що таке `autocommit_block`"
    Звичайний `CREATE INDEX` блокує запис у таблицю, поки індекс будується; на великій таблиці це хвилини, і всі збори
    новин чекають. `CREATE INDEX CONCURRENTLY` будує індекс без цього блокування, але **не може виконуватися в
    транзакції**, а Alembic загортає кожну міграцію в транзакцію. `with op.get_context().autocommit_block():` —
    тимчасово виходить з неї. Якщо `CONCURRENTLY` впав посередині, лишається «невалідний» індекс — звідси
    `IF NOT EXISTS` і `DROP INDEX CONCURRENTLY IF EXISTS` у `downgrade()`.

??? tip "Індекс з класом операторів у моделі"
    `Index(name, "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"})`. На SQLite
    `postgresql_*` ігноруються — `create_all` створить звичайний індекс на `title`, як і міграція.

??? tip "`create_all` і розширення"
    `Base.metadata.create_all` не виконує міграцій, тож `CREATE EXTENSION` із `0005` у тестах не буде. Подія
    `before_create` на `Base.metadata` спрацьовує перед створенням таблиць — там і місце для
    `CREATE EXTENSION IF NOT EXISTS pg_trgm` (лише якщо `connection.dialect.name == "postgresql"`).

??? tip "`git apply` з підпапки нічого не робить"
    Якщо `lab_final` лежить усередині репозиторію книжки, `cd lab_final && git apply ../docs/labs/…patch` пише
    `Skipped patch 'news_hub/tables.py'` і нічого не змінює: шляхи в патчі git рахує від кореня репозиторію. Застосовуй
    з кореня: `git apply --directory=lab_final docs/labs/news_hub_search_index.patch`. Поза репозиторієм
    `cd lab_final && git apply /шлях/до/news_hub_search_index.patch` працює як звичайний `patch -p1`.

## Підхід до розв'язку { #solution }

??? success "Підхід до розв'язку"
    Повністю — у патчі [`news_hub_search_index.patch`](news_hub_search_index.patch) (нова міграція + зміни
    `tables.py`). Перевірка, що він лягає на твою копію, і застосування — з кореня репозиторію:

    ```bash
    git apply --check --directory=lab_final docs/labs/news_hub_search_index.patch
    git apply --directory=lab_final docs/labs/news_hub_search_index.patch
    ```

    Міграція:

    ```python title="migrations/versions/0005_search_index.py (фрагмент)"
    def upgrade() -> None:
        # (chat_id) — початок UNIQUE (chat_id, keyword): пошук за chat_id іде по унікальному індексу
        op.drop_index("ix_subscriptions_chat_id", table_name="subscriptions")
        if op.get_bind().dialect.name != "postgresql":                # SQLite (тести): звичайний індекс
            op.create_index("ix_news_title_trgm", "news", ["title"])
            return
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        with op.get_context().autocommit_block():
            op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_news_title_trgm "
                       "ON news USING gin (title gin_trgm_ops)")


    def downgrade() -> None:
        if op.get_bind().dialect.name == "postgresql":
            with op.get_context().autocommit_block():
                op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_news_title_trgm")
        else:
            op.drop_index("ix_news_title_trgm", table_name="news")
        op.create_index("ix_subscriptions_chat_id", "subscriptions", ["chat_id"])
    ```

    Модель:

    ```python title="news_hub/tables.py (фрагмент)"
    class NewsRow(Base):
        ...
        # search() — title.icontains(q): на PostgreSQL це `title ILIKE '%…%'` → trigram-індекс на title (міграція 0005)
        __table_args__ = (Index("ix_news_title_trgm", "title", postgresql_using="gin",
                                postgresql_ops={"title": "gin_trgm_ops"}),)


    class SubscriptionRow(Base):
        ...
        chat_id: Mapped[int] = mapped_column(BigInteger)          # без index=True


    # create_all (тести на PostgreSQL) теж має знати про розширення: без нього gin_trgm_ops не існує
    @event.listens_for(Base.metadata, "before_create")
    def create_pg_trgm(target: object, connection: Connection, **kw: Any) -> None:
        if connection.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    ```

    Три деталі, кожну з яких показав прогін, а не читання коду:

    1. **Індекс — і в моделі.** Лише міграція без змін у `tables.py` → на PostgreSQL:
       ```text
       FAILED: New upgrade operations detected: [('remove_index', Index('ix_news_title_trgm', Column('title', VARCHAR(length=300), …))), ('add_index', Index('ix_subscriptions_chat_id', …))]
       ```
       Це той самий `alembic check`, що в job `postgres` ([крок 12](../tutorials/12_ci_cd/what_to_check.md#alembic-check)).
    2. **Розширення — і для `create_all`.** Без слухача `before_create` тести на чистій базі PostgreSQL падають:
       ```text
       asyncpg.exceptions.UndefinedObjectError: operator class "gin_trgm_ops" does not exist for access method "gin"
       ```
    3. **Вираз — як у запиті.** Варіант з `gin (lower(title) gin_trgm_ops)` проходить `alembic check` і всі 363 старі
       тести — але `test_search_condition_uses_trigram_index` показує `Seq Scan … Filter: ((title)::text ~~* …)`. Зелені
       тести без перевірки плану цю помилку пропустили б.

## Що перевірити самому { #self-check }

- [ ] `EXPLAIN ANALYZE` на своїх даних: рідкісне слово, часте слово, слово з `%` (`autoescape` — `ESCAPE '/'` у плані).
- [ ] Що зміниться в плані, якщо переписати `search()` на `func.lower(NewsRow.title).contains(q.lower())`? Який індекс
      тоді потрібен — і чому саме тому так важливо, щоб тест компілював ту саму умову, що й код?
- [ ] Скільки займає індекс (`SELECT pg_size_pretty(pg_relation_size('ix_news_title_trgm'))`) і скільки — таблиця?
- [ ] Наскільки повільніше став збір: заміряй `POST /api/scrape` з індексом і без (кожна вставка оновлює GIN).
- [ ] `alembic downgrade -1` на PostgreSQL — `\d subscriptions` знову показує `ix_subscriptions_chat_id`.
- [ ] Чому `ix_subscriptions_chat_id` зайвий, а `uq_subscription_chat_keyword` — ні? Покажи `EXPLAIN` запиту
      `for_chat()`.

## Після лаби: власне розширення { #own-project }

Фінальна робота — твоє розширення News Hub (або власний проєкт на тому самому стеку). Оцінюється не обсяг коду, а
**твої** рішення: що додав, як перевірив, що виміряв.

| | Обов'язково | Бажано |
|---|---|---|
| код | пакет з модулями за відповідальністю, типи в публічних функціях | `mypy --strict` |
| дані | PostgreSQL або SQLite + міграції Alembic; обмеження в схемі (`UNIQUE`, `CHECK`, FK) | Redis для кешу чи лічильників |
| інтерфейс | REST API **або** бот | два інтерфейси над однією логікою, як API і бот у News Hub |
| тести | логіка + API; тест, що ловить помилку, яку ти справді зробив | тест плану запиту чи кількості запитів |
| запуск | `README.md`: як запустити за 5 хвилин; `.env.example` без секретів | `Dockerfile` + `docker-compose.yml` |
| CI | тести на кожен PR | образ + smoke-тест |
| безпека | секрети лише зі змінних середовища; перевірка доступу до чужих даних | rate limit; SSRF-захист, якщо є завантаження з URL |

Теми, які добре лягають на News Hub: нове RSS-джерело + trigram-пошук + щоденний дайджест LLM у Telegram; монітор цін
(скрапер + кеш + сповіщення ботом); keyset-пагінація стрічки для нескінченного скролу.

### План роботи { #plan }

| Етап | Результат | Перевірка |
|---|---|---|
| 1. ідея | README: проблема, користувач, 3–5 функцій MVP | можна пояснити за 30 секунд |
| 2. скелет | репозиторій, пакет, залежності, перший тест, CI | зелена галочка на першому PR |
| 3. дані | моделі, міграції, обмеження | `alembic check` у CI |
| 4. функції MVP | ендпоінти чи команди бота, кожна — з тестом | тести в CI |
| 5. запуск | `Dockerfile`, `docker-compose.yml`, `.env.example` | `docker compose up --wait` на чистій машині |
| 6. аудит | індекси під справжні запити, `EXPLAIN` | план показує індекс там, де ти його чекаєш |
| 7. захист | 5–7 хвилин, демо | чекліст нижче |

## Захист проєкту { #defense }

5–7 хвилин, з демо. Структура:

1. **Проблема** (30–60 с): одна конкретна людина, її ситуація і скільки їй коштує проблема. Не «багато людей
   мають проблему з новинами».
2. **Рішення** (30 с): три кроки користувача, а не список технологій.
3. **Демо** (2–3 хв): **один** сценарій від дії користувача до результату, не екскурсія по ендпоінтах.
4. **Як це працює** (1 хв): одна діаграма — компоненти і де живе стан — і **одне рішення з доказом**: як ти його
   виміряв. «У мене 367 тестів» — факт; «пошук на 200 тисячах новин займав 81 мс, після trigram-індексу — 0.04 мс,
   `EXPLAIN ANALYZE`, PostgreSQL 16» — історія, яку запам'ятають.
5. **Що є і що далі** (30 с): чесно відділи зроблене від планів; наступні кроки — вимірювані.

### Чекліст перед виступом { #defense-checklist }

- [ ] Стек піднято **до** виступу: `docker compose up --wait`, smoke-скрипт зелений.
- [ ] Дані підготовлені: фікстури, знімок сайту, двійник Telegram — жодного «зараз зареєструюсь».
- [ ] Є запасний план — відео того самого сценарію: мережа падає саме тоді, коли потрібна.
- [ ] Великий шрифт у терміналі й браузері; ≤ 12 слайдів, одна ідея на слайд.
- [ ] CI зелений на останньому коміті; посилання на репозиторій — на слайді.
- [ ] У README і на слайдах — лише те, що справді працює; плани позначені як плани.
- [ ] Числа — з виміру (команда, дані, версія), припущення позначені як припущення.

### Питання, до яких варто підготуватися { #defense-questions }

1. Хто вже користується? З ким ти говорив про проблему?
2. Чим це краще за те, що люди роблять зараз?
3. Скільки коштує один користувач (сервер, виклики LLM)?
4. Що буде, якщо сайт-джерело змінить верстку чи закриє RSS?
5. Що було найважчим і як ти це розв'язав?
6. Як ти знаєш, що код працює? Що саме перевіряють тести — і чого вони **не** перевіряють?
7. Що зробив би інакше, якби починав з нуля?

Структура відповіді: коротка пряма відповідь → один факт → що зробиш далі. «Не знаю, перевірю так-то» — сильна
відповідь; вигадана цифра — слабка, її перевірять.
