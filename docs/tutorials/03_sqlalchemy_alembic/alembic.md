# Міграції Alembic

> Крок 3 · розділ 5 з 5. Код: [`migrations/versions/0001_news_table.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/migrations/versions/0001_news_table.py), [`migrations/env.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/migrations/env.py), [`alembic.ini`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/alembic.ini), [`docker-compose.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/docker-compose.yml).
> Теорія: [Частина V. Бази даних → міграції Alembic](../../05_databases/README.md).

## Задача { #task }

Таблиця `news` має з'явитися в базі. Найпростіше — `Base.metadata.create_all()`: він створює таблиці, яких немає. Але **не змінює наявні**. У [кроці 7](../07_llm_api/index.md) у таблиці з'являться стовпці для підсумку від LLM, і база з тисячами новин має отримати їх **без втрати даних**. А на кожному комп'ютері й сервері схема має бути однакова.

Для цього — **міграції**: версії схеми як код, у git поруч із програмою. Кожна міграція знає, як перейти на крок уперед (`upgrade`) і назад (`downgrade`). Так само працюють `makemigrations`/`migrate` у Django.

| | `Base.metadata.create_all()` | Alembic |
|---|---|---|
| створити таблицю | так | так |
| додати стовпець до наявної таблиці | ні | так |
| відкотити зміну | ні | `alembic downgrade -1` |
| яка версія схеми в базі | невідомо | таблиця `alembic_version` |
| де використовується в кроці | `tests/conftest.py`: порожня база на кожен тест | сервер і розробка |

## Зміна 1: Alembic бере адресу бази з застосунку { #env }

```python title="migrations/env.py (фрагмент)"
from news_hub import tables  # noqa: F401 — імпорт реєструє таблицю news у Base.metadata
from news_hub.db import DATABASE_URL, Base

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=connection.dialect.name == "sqlite")   # SQLite не вміє ALTER COLUMN
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(DATABASE_URL, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()
```

| Рядок | Навіщо |
|---|---|
| `from news_hub import tables` | без імпорту `Base.metadata` порожній, і autogenerate «не бачить» таблиці `news` |
| `DATABASE_URL` з `news_hub.db` | застосунок і міграції **завжди** дивляться в ту саму базу; в `alembic.ini` адреси немає |
| `create_async_engine` + `run_sync` | драйвери async (`asyncpg`, `aiosqlite`), а Alembic працює синхронно — `run_sync` з'єднує їх |
| `poolclass=pool.NullPool` | міграція — разова дія, пул з'єднань не потрібен |
| `render_as_batch=...` | SQLite не вміє більшість `ALTER TABLE`; batch-режим перебудовує таблицю: створює нову, копіює дані, міняє місцями |

В `alembic.ini` — лише `script_location = migrations`, `prepend_sys_path = .` (щоб `import news_hub` працював з папки кроку), шаблон імен файлів `%%(rev)s_%%(slug)s` і налаштування журналу.

## Зміна 2: перша міграція { #migration-0001 }

```python title="migrations/versions/0001_news_table.py (фрагмент)"
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('news',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    ...
    sa.Column('scraped_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('url')
    )
    op.create_index(op.f('ix_news_category'), 'news', ['category'], unique=False)
    op.create_index(op.f('ix_news_lang'), 'news', ['lang'], unique=False)
    op.create_index(op.f('ix_news_source'), 'news', ['source'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_news_source'), table_name='news')
    op.drop_index(op.f('ix_news_lang'), table_name='news')
    op.drop_index(op.f('ix_news_category'), table_name='news')
    op.drop_table('news')
```

- `revision` / `down_revision` — версія і попередня версія. Міграції утворюють ланцюжок: `None → 0001 → 0002 → …`.
- `downgrade` — дзеркало `upgrade` у зворотному порядку: спершу індекси, потім таблиця.

Команди (з папки кроку):

```bash
alembic revision --autogenerate --rev-id 0001 -m "news table"   # порівняти NewsRow з базою → файл міграції
alembic upgrade head                                            # застосувати всі нові міграції
alembic downgrade -1                                            # відкотити останню
alembic current                                                 # яка версія в базі
alembic history                                                 # усі міграції
alembic check                                                   # чи збігаються моделі з базою
```

Що робить `alembic upgrade head`, покроково:

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph S0 ["1. налаштування"]
        direction LR
        a0["alembic.ini<br>script_location"] --> a1["migrations/env.py"] --> a2["DATABASE_URL<br>з news_hub.db"]
    end
    subgraph S1 ["2. де база зараз"]
        direction LR
        b0["SELECT version_num<br>FROM alembic_version"] --> b1{"таблиця є?"}
        b1 -- ні --> b2["нова база<br>версія: base"]
        b1 -- так --> b3["версія, напр. 0001"]
    end
    subgraph S2 ["3. що застосувати"]
        direction LR
        c0["ланцюжок<br>down_revision"] --> c1["від поточної<br>до head"]
    end
    subgraph S3 ["4. застосувати"]
        direction LR
        d0["upgrade() кожної<br>по черзі"] --> d1["alembic_version<br>= head"]
    end
    S0 --> S1 --> S2 --> S3

    class a0,a1,b0,c0,c1,d0 step
    class a2 warning
    class b1 decision
    class b2,b3 step
    class d1 success
```

## Результат: міграція на SQLite і PostgreSQL { #result }

SQLite — файл у тимчасовій папці (`DATABASE_URL=sqlite+aiosqlite:///…/news_hub.db`):

```text
$ alembic upgrade head
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, news table — таблиця новин агрегатора (крок 3)
$ alembic current
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
0001 (head)
$ alembic history
<base> -> 0001 (head), news table — таблиця новин агрегатора (крок 3)
$ alembic downgrade -1
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade 0001 -> , news table — таблиця новин агрегатора (крок 3)
```

Після `downgrade -1` `alembic current` нічого не друкує, крім рядків `INFO`: база знову на версії `base`, таблиці `news` немає.

PostgreSQL 16 (`DATABASE_URL=postgresql+asyncpg://news:news@…/news_hub`):

```text
$ alembic upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, news table — таблиця новин агрегатора (крок 3)
$ alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
0001 (head)
$ alembic check
...
No new upgrade operations detected.
```

«Transactional DDL» у PostgreSQL означає, що навіть `CREATE TABLE` іде в транзакції: міграція, що впала посередині, відкочується повністю. SQLite так не вміє («non-transactional DDL») — на ній половина міграції може лишитися застосованою.

### SQL міграції без бази { #offline }

`--sql` — «офлайн»-режим: Alembic друкує SQL, нічого не виконуючи. Так перевіряють міграцію перед запуском на сервері або віддають SQL адміністратору бази:

```text
$ alembic upgrade head --sql
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE news (
    id SERIAL NOT NULL,
    url VARCHAR(500) NOT NULL,
    title VARCHAR(300) NOT NULL,
    source VARCHAR(100) NOT NULL,
    lang VARCHAR(2) NOT NULL,
    category VARCHAR(100) NOT NULL,
    published_time TIME WITHOUT TIME ZONE,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (url)
);

CREATE INDEX ix_news_category ON news (category);

CREATE INDEX ix_news_lang ON news (lang);

CREATE INDEX ix_news_source ON news (source);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;
```

(Рядки `INFO` Alembic пише в stderr, тож у файл `> migration.sql` вони не потраплять.)

Видно `alembic_version` — службову таблицю з одним рядком: номером поточної версії. Саме її читає крок 2 на схемі вище.

## Autogenerate — чернетка, а не готова міграція { #autogenerate }

`alembic revision --autogenerate` порівнює `Base.metadata` з базою і пише файл міграції. Перевірили, що він пише для `NewsRow` на порожній базі PostgreSQL (у копії кроку, без файлу `0001`):

```text
INFO  [alembic.autogenerate.compare.tables] Detected added table 'news'
INFO  [alembic.autogenerate.compare.constraints] Detected added index 'ix_news_category' on '('category',)'
INFO  [alembic.autogenerate.compare.constraints] Detected added index 'ix_news_lang' on '('lang',)'
INFO  [alembic.autogenerate.compare.constraints] Detected added index 'ix_news_source' on '('source',)'
Generating …/migrations/versions/0001_news_table.py ...  done
```

```python title="згенерований рядок"
sa.Column('scraped_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
```

`sa.text('now()')` — **текст функції PostgreSQL**. Alembic прочитав з бази, як вона описує значення за замовчуванням, і переписав дослівно. На SQLite з такою міграцією `alembic upgrade head` проходить, але перший же `INSERT` падає:

```text
OperationalError unknown function: now()
```

Тому в міграції кроку рядок виправлено вручну на `server_default=sa.func.now()` — SQLAlchemy підставляє правильний SQL для кожної бази (`now()` у PostgreSQL, `CURRENT_TIMESTAMP` у SQLite, [розділ 1](engine_and_table.md#table)). Про це — docstring самої міграції.

!!! warning "Autogenerate не все бачить"
    Autogenerate знаходить нові таблиці, стовпці, індекси, обмеження. Але, наприклад, **перейменування** стовпця він бачить як «видалити старий + додати новий» — з утратою даних. Правило: **кожну автоміграцію читай перед комітом**, а `alembic check` покаже, чи збігаються моделі з базою.

## PostgreSQL для розробки: `docker-compose.yml` { #compose }

```yaml title="docker-compose.yml"
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: news_hub
      POSTGRES_USER: news
      POSTGRES_PASSWORD: news          # лише для навчання на своєму комп'ютері
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data   # дані переживають перезапуск контейнера
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U news -d news_hub"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  pgdata:
```

```bash
docker compose up -d db
export DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub
alembic upgrade head && uvicorn news_hub.api:app --reload
```

- `volumes: pgdata` — дані живуть у томі Docker, а не в контейнері: `docker compose down` і `up` їх не стирають (`down -v` — стирає).
- `healthcheck` з `pg_isready` — Docker знає, коли база справді готова приймати з'єднання.
- Пароль `news` — лише для свого комп'ютера. Секрети в змінних середовища — [крок 8](../08_security/index.md), сам застосунок у контейнері — [крок 10](../10_docker/index.md).

## Правило { #rule }

!!! tip "Правило"
    Схему бази змінюй лише міграціями: `tables.py` каже, якою таблиця має бути, `migrations/` — як до цього дійти. Autogenerate — чернетка: прочитай файл, перевір на обох базах, `alembic check` — і лише тоді комітом у git.

**Далі:** [Контрольна точка](checkpoint.md) — тести, практика, самоперевірка.
