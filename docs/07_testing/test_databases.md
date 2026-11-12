# Тести з базою даних: SQLite чи PostgreSQL, транзакція на тест, паралельність

## Проблема { #problem }

Репозиторій і ендпоінти пишуть у базу, і перевірити їх без бази не вийде: мок сесії перевірить лише те, що код викликав `session.add`, а не те, що `UNIQUE` спрацював, пошук знайшов кирилицю, а `ROLLBACK` не зачепив уже збережене. Але справжня база в тестах — це три нові питання:

- **яка база?** SQLite у пам'яті не потребує сервера і створюється за мілісекунди, але це інша СУБД, ніж PostgreSQL у продакшені;
- **як ізолювати тести?** Новина, яку записав один тест, не має бути видна наступному — інакше результат залежить від порядку;
- **як не заважати один одному паралельно?** Два процеси pytest на одній базі створюють ті самі таблиці й ті самі рядки.

## Ментальна модель { #mental-model }

Найшвидший спосіб ізоляції — **транзакція на тест**: таблиці створюються раз на прогін, кожен тест працює всередині зовнішньої транзакції, а після тесту її відкочують. Код, що тестується, може робити `commit` — він закриває лише точку збереження (`SAVEPOINT`), а не зовнішню транзакцію:

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph S1 ["1. engine, scope session"]
        direction LR
        A1["create_all<br>раз на прогін"]
    end
    subgraph S2 ["2. фікстура db: початок тесту"]
        direction LR
        B1["connect()"] --> B2["BEGIN<br>зовнішня транзакція"] --> B3["Session(create_savepoint)<br>SAVEPOINT"]
    end
    subgraph S3 ["3. тест"]
        direction LR
        C1["INSERT уряд-ухвалив-бюджет"] --> C2["session.commit()<br>RELEASE SAVEPOINT"] --> C3["count = 1"]
    end
    subgraph S4 ["4. фікстура db: кінець тесту"]
        direction LR
        D1["ROLLBACK<br>зовнішньої транзакції"] --> D2["таблиця порожня"]
    end
    subgraph S5 ["5. наступний тест"]
        direction LR
        E1["count = 0<br>на старті"]
    end
    S1 --> S2 --> S3 --> S4 --> S5

    class A1,B1,B2,C1,C3 step
    class B3,C2 warning
    class D1 decision
    class D2,E1 success
```

| Стратегія ізоляції | Швидкість | Що бачить тест | Коли |
|---|---|---|---|
| нова база на тест (SQLite у пам'яті, новий engine) | швидко лише для SQLite | усе справжнє, включно з `COMMIT` | SQLite; код, що сам відкриває з'єднання |
| `create_all` / `drop_all` на тест | повільно на PostgreSQL | усе справжнє | мало тестів |
| `TRUNCATE` після тесту | середньо | усе справжнє | код з кількома з'єднаннями (фонові задачі) |
| транзакція на тест + `ROLLBACK` | найшвидше | лише те, що йде через **це** з'єднання | більшість тестів репозиторію й API |

Код — [`tests/conftest.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/testing/tests/conftest.py), [`tests/test_db.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/testing/tests/test_db.py), [`newsapp/storage.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/testing/newsapp/storage.py), [`demos/sqlite_vs_postgres.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/testing/demos/sqlite_vs_postgres.py) у [`examples/testing`](https://github.com/NikoriakViktor/news_hub/tree/main/examples/testing).

## SQLite у пам'яті проти PostgreSQL { #sqlite-vs-postgres }

Ті самі запити на двох базах, обидві — з налаштуваннями за замовчуванням:

```text
$ python demos/sqlite_vs_postgres.py postgresql+psycopg://test:test@localhost:5432/test
--- sqlite
   VARCHAR(5) ← 'rbc.ua.com'        rbc.ua.com
   INTEGER ← 'abc'                  abc
   REFERENCES без батька            вставлено
   'FastAPI' LIKE 'fastapi'         1
   lower('УРЯД') без налаштувань    УРЯД
--- postgresql
   VARCHAR(5) ← 'rbc.ua.com'        DataError: value too long for type character varying(5)
   INTEGER ← 'abc'                  DataError: invalid input syntax for type integer: "abc"
   REFERENCES без батька            IntegrityError: insert or update on table "c" violates foreign key constraint "c_p_id_fkey"
   'FastAPI' LIKE 'fastapi'         False
   lower('УРЯД') без налаштувань    уряд
```

| Що | SQLite | PostgreSQL | Наслідок для тестів |
|---|---|---|---|
| довжина `VARCHAR(n)` | не перевіряє | `DataError` | задовгий рядок «зберігся» в тесті й упав у продакшені |
| типи колонок | «спорідненість»: рядок ляже в `INTEGER` | суворі | помилку типу видно лише на PostgreSQL |
| зовнішні ключі | вимкнені, поки не `PRAGMA foreign_keys=ON` | завжди | сирітські рядки в тестах не помітні |
| `LIKE` | без регістру, але лише для латиниці | з регістром; `ILIKE` — без | пошук поводиться по-різному |
| `lower()`, `upper()` | лише ASCII | Unicode | пошук без регістру не працює з кирилицею |
| одночасні записи | одна транзакція на запис для всієї бази | рядкові блокування | гонок і `deadlock` на SQLite не видно |
| специфічні типи | немає `JSONB`, масивів, `ARRAY`, повнотекстового пошуку | є | код з ними на SQLite не запуститься |

SQLite лишається гарною базою для **більшості** тестів: секунди замість хвилин, без сервера, без налаштувань CI. Але SQL конкретної СУБД вона не перевіряє. Тому розумний розподіл: звичайний прогін — SQLite; той самий набір тестів хоча б раз на кожну зміну (у CI) — справжній PostgreSQL через змінну середовища:

```python title="tests/conftest.py (фрагмент)"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
```

```text
$ pytest -q
68 passed, 1 skipped, 1 deselected in 1.23s
$ TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:5432/test pytest -q
69 passed, 1 deselected in 0.58s
```

Тест, що має сенс лише на PostgreSQL, позначено маркером і на SQLite пропущено з причиною ([Основи pytest, маркери](pytest_basics.md#markers)):

```python title="tests/test_db.py (фрагмент)"
@pytest.mark.postgres
def test_too_long_source_is_rejected_by_database(db: Session, make_article: Callable[..., Article]) -> None:
    """VARCHAR(20): PostgreSQL відхиляє 21 символ. SQLite мовчки зберігає — тому тест лише для PostgreSQL."""
    with pytest.raises(DataError, match="too long"):
        make_article(source="x" * 21)
```

Перевірка довжини в API все одно є (Pydantic, `max_length=20` → `422`). Тест бази доводить інше: навіть якщо рядок прийде в обхід API, база його не збереже.

### Вирівняти SQLite з продакшеном { #sqlite-tuning }

Частину відмінностей можна прибрати налаштуваннями з'єднання — подією `connect` у SQLAlchemy:

```python title="newsapp/storage.py (фрагмент)"
def _sqlite_connect(dbapi_connection: Any, _record: Any) -> None:
    # 1. sqlite3 сам відкриває й закриває транзакції і ламає SAVEPOINT: вимикаємо — BEGIN шле SQLAlchemy
    #    (рецепт з документації SQLAlchemy «Serializable isolation / Savepoints / Transactional DDL»)
    dbapi_connection.isolation_level = None
    # 2. вбудований lower() у SQLite знає лише латиницю: lower('УРЯД') == 'УРЯД'
    dbapi_connection.create_function("lower", 1, lambda s: s.lower() if isinstance(s, str) else s,
                                     deterministic=True)
```

```python
engine = create_engine(url, **options)
event.listen(engine, "connect", _sqlite_connect)
event.listen(engine, "begin", lambda conn: conn.exec_driver_sql("BEGIN"))
```

Так само вмикають зовнішні ключі: `dbapi_connection.execute("PRAGMA foreign_keys=ON")`. Перший пункт — не косметика, без нього не працює транзакція на тест ([нижче](#pysqlite-savepoint)).

`ArticleRepo.search` використовує `icontains` — SQLAlchemy перетворює його на `lower(title) LIKE lower(:q)`. Тест пошуку з кирилицею проходить на обох базах лише завдяки заміні `lower()`:

```python title="tests/test_db.py (фрагмент)"
def test_search_is_case_insensitive_for_cyrillic(db: Session, make_article: Callable[..., Article]) -> None:
    make_article(title="Уряд ухвалив бюджет")
    assert [a.title for a in ArticleRepo(db).search("УРЯД")] == ["Уряд ухвалив бюджет"]
```

## Транзакція на тест { #transaction-per-test }

```python title="tests/conftest.py (фрагмент)"
@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Одна база на весь прогін: таблиці створюються раз, дані відкочуються після кожного тесту."""
    engine = make_engine(TEST_DATABASE_URL)
    ...
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    ...


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Транзакція на тест: усе, що записали тест і застосунок (навіть з COMMIT), відкочується."""
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        yield session
        session.close()
        transaction.rollback()
```

- `connection.begin()` — зовнішня транзакція, якою керує фікстура.
- `Session(bind=connection, join_transaction_mode="create_savepoint")` — сесія приєднується до вже відкритої транзакції і для своїх `commit`/`rollback` використовує `SAVEPOINT`. Без цього режиму `session.rollback()` у коді (як в ендпоінті після `IntegrityError`) відкотив би **всю** зовнішню транзакцію — разом з даними, підготовленими на початку тесту.
- `expire_on_commit=False` — після `commit` об'єкти не перечитуються з бази, як і в `sessionmaker` застосунку.
- Той самий `db` фікстура `client` передає в застосунок через `dependency_overrides[get_db]` ([Тестування FastAPI](testing_fastapi.md#overrides)): API пише в ту саму транзакцію, і після тесту від нього теж нічого не лишається.

```python title="tests/test_db.py (фрагмент)"
@pytest.mark.parametrize("run", [1, 2])
def test_commit_in_test_is_still_rolled_back(db: Session, run: int) -> None:
    """Обидва запуски бачать порожню таблицю: COMMIT закрив лише SAVEPOINT, зовнішню транзакцію відкотить фікстура."""
    assert count(db) == 0
    ArticleRepo(db).add("Уряд ухвалив бюджет", "rbc.ua")
    db.commit()
    assert count(db) == 1


def test_rollback_after_error_keeps_committed_data(db: Session, make_article: Callable[..., Article]) -> None:
    """Як ендпоінт POST /articles: перша новина закомічена, дубль → IntegrityError → rollback."""
    make_article(title="Уряд ухвалив бюджет")
    db.commit()
    with pytest.raises(IntegrityError):
        make_article(title="Уряд ухвалив бюджет")
    db.rollback()
    assert count(db) == 1
```

Перший тест запускається двічі: другий запуск доводить, що `COMMIT` першого не пережив тест. Другий тест — сценарій ендпоінта `POST /articles` (`201`, `409`, перша новина на місці) на рівні репозиторію.

### Пастка SQLite: `SAVEPOINT` без рецепта { #pysqlite-savepoint }

Модуль `sqlite3` за замовчуванням сам вирішує, коли починати й завершувати транзакції, і на цьому ламаються вкладені `SAVEPOINT`. Ті самі фікстура і тести без рецепта з `_sqlite_connect`:

```text
$ pytest -q tests/test_db.py
E       assert 1 == 0
E        +  where 1 = count(<sqlalchemy.orm.session.Session object at 0x708195dd9a90>)
E       sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) UNIQUE constraint failed: articles.slug
E       [parameters: ('уряд-ухвалив-бюджет', 'Уряд ухвалив бюджет', 'rbc.ua')]
FAILED tests/test_db.py::test_commit_in_test_is_still_rolled_back[2] - assert...
FAILED tests/test_db.py::test_duplicate_slug_violates_unique - sqlalchemy.exc...
FAILED tests/test_db.py::test_rollback_after_error_keeps_committed_data - sql...
FAILED tests/test_db.py::test_search_is_case_insensitive_for_cyrillic - sqlal...
4 failed, 2 passed, 1 skipped in 0.46s
```

Перший запуск `[1]` зелений, другий бачить рядок першого: «відкат» нічого не відкотив, і далі кожен тест натикається на чужі новини. У повному наборі так падає 7 тестів, серед них і `test_duplicate_is_409_and_first_survives` з API: застосунок пише в ту саму «невідкатну» транзакцію. Окремий скрипт показує те саме без pytest:

```text
--- транзакція на тест у SQLite
   create_engine за замовчуванням   рядків після відкату: 1
   make_engine (рецепт SAVEPOINT)   рядків після відкату: 0
```

На PostgreSQL рецепт не потрібен: драйвер psycopg керує транзакціями так, як очікує SQLAlchemy.

### Межі транзакції на тест { #limits }

Відкат прибирає лише те, що пройшло через **це** з'єднання. Поза ним:

- **код, що відкриває власні сесії** — фонова задача з `sessionmaker` застосунку, другий потік, Celery-воркер. Його записи або не видно тесту (інша транзакція), або вони переживуть тест. Такому коду передають тестову фабрику сесій через залежність, або для таких тестів використовують окрему базу чи `TRUNCATE`.
- **семантика `COMMIT`** — що дані справді збереглися і їх видно з іншого з'єднання. Це перевіряє тест без підміни `get_db` ([Тестування FastAPI](testing_fastapi.md#real-dependencies)).
- **DDL** у СУБД без транзакційного DDL (MySQL): `CREATE TABLE` у тесті закомітить усе. PostgreSQL і SQLite DDL відкочують.
- **async-engine** працює так само (`AsyncSession(bind=connection, join_transaction_mode="create_savepoint")`), але engine, з'єднання і тест мають жити в одному циклі подій — scope async-фікстур має це враховувати.

## Схема: `create_all` проти міграцій { #migrations }

Тести будують таблиці з моделей (`Base.metadata.create_all`), а продакшен — міграціями Alembic. Якщо модель і міграції розійшлися (додали поле в модель, забули міграцію), тести зелені, а `alembic upgrade head` дає іншу схему. Тому окремо перевіряють самі міграції: `alembic upgrade head` на порожній базі і `alembic check` — «чи немає різниці між моделями й міграціями» ([крок 12, «`alembic check`»](../tutorials/12_ci_cd/what_to_check.md#alembic-check)).

## Фабрики й обмеження бази { #factories }

Дані для тестів готує фабрика `make_article` ([Фікстури, фабрики](fixtures.md#factories)): у тесті видно лише поля, важливі для перевірки. Окремий клас тестів — **обмеження самої бази**, бо саме їх не бачать моки й не завжди бачить SQLite:

```python title="tests/test_db.py (фрагмент)"
def test_duplicate_slug_violates_unique(db: Session, make_article: Callable[..., Article]) -> None:
    make_article(title="Уряд ухвалив бюджет")
    with pytest.raises(IntegrityError):
        make_article(title="Уряд ухвалив бюджет!")        # slug той самий: уряд-ухвалив-бюджет


def test_search_treats_percent_literally(db: Session, make_article: Callable[..., Article]) -> None:
    make_article(title="Інфляція 5% за рік")
    make_article(title="Інфляція сповільнилась")
    assert [a.title for a in ArticleRepo(db).search("5%")] == ["Інфляція 5% за рік"]
    assert ArticleRepo(db).search("%") == [ArticleRepo(db).get("інфляція-5-за-рік")]
```

Другий тест перевіряє `autoescape=True`: `%` від користувача — звичайний символ, а не «будь-що». Без нього пошук `%` повернув би всі новини.

## Паралельні тести: `pytest-xdist` { #parallel }

```text
$ pytest -q -n 2
68 passed, 1 skipped in 1.13s
```

`-n 2` запускає два процеси-воркери (`gw0`, `gw1`) і роздає їм тести. Кожен процес має свій інтерпретатор: свій `app`, свій `app.dependency_overrides`, свою SQLite у пам'яті, тож для SQLite нічого міняти не треба. (Підсумок xdist не рахує `deselected` — тест `slow` і тут не запускався.)

Зі спільним PostgreSQL обидва воркери створюють і видаляють ті самі таблиці в одній схемі. Ось той самий прогін, якщо схема спільна:

```text
$ TEST_DATABASE_URL=postgresql+psycopg://… pytest -q -n 2      # schema = "test_shared"
E           psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "pg_namespace_nspname_index"
E           DETAIL:  Key (nspname)=(test_shared) already exists.
E           [SQL: CREATE SCHEMA "test_shared"]
61 passed, 8 errors in 1.67s
```

Результат різний від запуску до запуску: в інших прогонах зіткнувся не `CREATE SCHEMA`, а `CREATE TABLE test_shared.articles` (`Key (typname, typnamespace)=(articles, …) already exists`). Помилки — в підготовці (`ERROR at setup`), тож червоніють випадкові тести, що першими попросили базу. Розв'язок — окрема схема (або окрема база) на воркер. xdist кладе ім'я воркера в змінну середовища `PYTEST_XDIST_WORKER` (і у фікстуру `worker_id`):

```python title="tests/conftest.py (фрагмент)"
WORKER = os.getenv("PYTEST_XDIST_WORKER", "main")       # pytest -n 2 → gw0, gw1: у кожного своя схема
...
    schema = f"test_{WORKER}"
    postgres = engine.dialect.name == "postgresql"
    if postgres:                                            # паралельні воркери — кожен у своїй схемі
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = engine.execution_options(schema_translate_map={None: schema})
```

```text
$ TEST_DATABASE_URL=postgresql+psycopg://… pytest -q -n 2
69 passed in 1.29s
```

`schema_translate_map={None: schema}` підставляє схему в усі таблиці без схеми — і в `CREATE TABLE`, і в запитах. Після прогону фікстура видаляє свою схему.

Паралельність — ще й перевірка незалежності тестів: xdist роздає тести воркерам не по файлах, тож тест, що покладається на стан після попереднього тесту того самого файлу, тут почне падати. `--dist loadfile` тримає файл в одному воркері, але це лікує симптом, а не причину.

## У News Hub { #news-hub }

- **Нова база на тест замість відкату.** News Hub працює з async SQLAlchemy, і клас `TestDatabase` для кожного тесту створює новий engine на `sqlite+aiosqlite://` зі `StaticPool` (одне з'єднання — інакше база в пам'яті зникає між запитами) і робить `drop_all` + `create_all` ([крок 5, «спільна `TestDatabase`»](../tutorials/05_api_testing/async_client.md#test-database)). Для SQLite у пам'яті це майже безкоштовно, і так фонові задачі, що відкривають власні сесії через `get_session_factory`, теж пишуть у тестову базу.
- **`TEST_DATABASE_URL` і `TEST_REDIS_URL`** — ті самі тести на PostgreSQL 16 і Redis 7; у CI це окремий job з `services` ([крок 12, «PostgreSQL і Redis у `services`»](../tutorials/12_ci_cd/what_to_check.md#postgres)). Базу `news_hub_test` створюють заздалегідь, а Redis-базу 15 тест очищує сам.
- **`lower()` для кирилиці.** `make_engine` у [`news_hub/db.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/news_hub/db.py) реєструє для SQLite той самий Unicode-`lower()`, що й приклад; тест `test_search_is_case_insensitive_and_literal` шукає `"ЗЕЛЕНСЬК"` і `"%%"` ([`tests/integration/test_crud.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/tests/integration/test_crud.py)).
- **Справжній `get_db` без підміни** — `tests/integration/test_db.py` викликає генератор залежності вручну (`anext`, `athrow`), як це робить FastAPI, і перевіряє `COMMIT` і `ROLLBACK` ([крок 5, «Справжній `get_db`»](../tutorials/05_api_testing/coverage.md#real-get-db)).
- **Гілка PostgreSQL без сервера.** `test_postgres_engine_gets_pool_settings` створює engine для `postgresql+asyncpg://…` і перевіряє налаштування пулу — engine не відкриває з'єднання, поки його не попросять.
- **Міграції** перевіряє CI: `alembic upgrade head` і `alembic check` на PostgreSQL ([крок 12](../tutorials/12_ci_cd/what_to_check.md#alembic-check)).

## Типові помилки { #mistakes }

| Помилка | Наслідок | Як правильно |
|---|---|---|
| лише SQLite, ніколи PostgreSQL | довжина, типи, FK, регістр, гонки — неперевірені | той самий набір на PostgreSQL хоча б у CI |
| `sqlite://` без `StaticPool` | кожне з'єднання — нова порожня база: `no such table` | `poolclass=StaticPool` для бази в пам'яті |
| транзакція на тест на pysqlite без рецепта | «відкат» нічого не відкочує, тести бачать чужі дані | `isolation_level = None` + `BEGIN` у події `begin` |
| `Session(bind=connection)` без `create_savepoint` | `rollback()` у коді відкочує і дані підготовки | `join_transaction_mode="create_savepoint"` |
| фонова задача з власною сесією в тесті з відкатом | записи поза транзакцією: невидимі або переживають тест | тестова фабрика сесій через залежність |
| `create_all` у тестах — і нічого про міграції | модель і міграції розходяться непомітно | `alembic upgrade head` + `alembic check` у CI |
| спільна схема для `pytest -n` | `UniqueViolation` на `CREATE`, випадкові падіння | схема чи база на воркер (`PYTEST_XDIST_WORKER`) |
| `TEST_DATABASE_URL` вказує на робочу базу | `drop_all` видалить таблиці | окрема база для тестів; ім'я з `_test` |

## Налагодження { #debugging }

- **Які SQL виконуються:** `create_engine(url, echo=True)` або `logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)` — видно `BEGIN`, `SAVEPOINT`, `RELEASE`, `ROLLBACK`. Якщо після тесту немає `ROLLBACK`, дані переживуть тест.
- **Тест бачить чужі дані:** запусти його окремо (`-k`). Окремо зелений — шукай, хто комітить поза транзакцією фікстури.
- **`no such table`:** база в пам'яті без `StaticPool`, або engine з іншого `lifespan`, який уже закрили.
- **Зависання на PostgreSQL:** незавершена транзакція іншого тесту тримає блокування (`SELECT * FROM pg_stat_activity WHERE state = 'idle in transaction'`).
- **Різні результати на SQLite і PostgreSQL:** прожени `demos/sqlite_vs_postgres.py` — і порівняй з таблицею відмінностей вище.

## Безпека { #security }

- **Тестова база — окрема.** Фікстура робить `drop_all` і `DROP SCHEMA … CASCADE`; адреса продакшен-бази в `TEST_DATABASE_URL` означає втрату даних. Надійніше, коли фікстура перевіряє ім'я бази (наприклад, закінчення `_test`) і відмовляється працювати з іншою.
- **Тестові облікові дані — несправжні** (`test:test`), а сервер бази для тестів не відкритий у мережу.
- **Дампи продакшену в тестах** містять персональні дані. Тестові дані будують фабриками, а не копіюють з бази користувачів.

## Питання { #questions }

1. Назви три речі, які SQLite пропускає, а PostgreSQL — ні.
2. Що робить `join_transaction_mode="create_savepoint"` і що буде без нього?
3. Чому без рецепта `isolation_level = None` другий запуск `test_commit_in_test_is_still_rolled_back` бачить рядок першого?
4. Що тест з транзакцією на тест **не** може перевірити?
5. Чому `pytest -n 2` на SQLite у пам'яті працює без змін, а на PostgreSQL — ні?
6. Навіщо перевіряти міграції окремо, якщо тести зелені?
7. Чому News Hub створює нову базу на кожен тест, а не відкочує транзакцію?

??? success "Відповіді"

    1. Довжину `VARCHAR`, тип колонки (рядок в `INTEGER`), зовнішні ключі; ще — регістр кирилиці в `lower()` і `LIKE`.
    2. Сесія використовує `SAVEPOINT` для своїх `commit`/`rollback` усередині зовнішньої транзакції фікстури. Без нього `rollback()` у коді відкочує всю зовнішню транзакцію разом з даними підготовки.
    3. `sqlite3` сам керує транзакціями і ламає `SAVEPOINT`: `COMMIT` у тесті закомітив зовнішню транзакцію, і відкочувати фікстурі вже нічого.
    4. Що дані справді збережені й видні з іншого з'єднання, і роботу коду, що відкриває власні сесії (фонові задачі, інші процеси).
    5. Кожен воркер — окремий процес зі своєю базою в пам'яті; PostgreSQL спільний, і воркери створюють ті самі таблиці в одній схемі.
    6. Тести будують схему з моделей, а продакшен — міграціями; розбіжність тести не бачать.
    7. З async-engine і SQLite у пам'яті нова база коштує мілісекунди, а фонові задачі відкривають власні сесії — їхні записи потрапляють у тестову базу без жодних трюків з транзакціями.

## Що далі { #next }

[Якість тестів: покриття, мутації, мінімальні версії, рецензія AI-коду](quality.md) — як дізнатися, що тести справді щось перевіряють.

**Джерела:** SQLAlchemy — [Joining a Session into an External Transaction (such as for test suites)](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites), [SQLite: Serializable isolation / Savepoints / Transactional DDL](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#serializable-isolation-savepoints-transactional-ddl), [Translation of Schema Names](https://docs.sqlalchemy.org/en/20/core/connections.html#translation-of-schema-names); SQLite — [Datatypes In SQLite](https://www.sqlite.org/datatype3.html), [Foreign Key Support](https://www.sqlite.org/foreignkeys.html), [`LIKE`](https://www.sqlite.org/lang_expr.html#like); [pytest-xdist](https://pytest-xdist.readthedocs.io/) (розділ «Identifying the worker process during a test»); PostgreSQL — [Character Types](https://www.postgresql.org/docs/current/datatype-character.html).
