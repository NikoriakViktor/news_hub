# Шари тестів: unit і integration

> Крок 5 · розділ 1 з 7. Код: [`tests/conftest.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/conftest.py), [`pytest.ini`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/pytest.ini), [`tests/integration/conftest.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/integration/conftest.py).
> Теорія: [Частина VII. Тестування API](../../07_testing/README.md); [піраміда тестів](https://nikoriakviktor.github.io/notes_chat_app/08_testing_and_quality/testing_foundations_full/) і [маркери pytest](https://nikoriakviktor.github.io/notes_chat_app/08_testing_and_quality/pytest_basics_full/) у Django-книзі.

## Задача { #task }

У кроці 4 тести лежать поруч: `test_models.py`, `test_parser.py`, `test_api.py`, `test_crud.py`, `test_redis.py`, а спільний `conftest.py` піднімає тестову базу й Redis. Щоб перевірити одну функцію парсера, pytest однаково збирає тести, які запускають застосунок, базу й Redis, і всім їм доступні фікстури бази.

Нам потрібні два режими:

- **після кожної зміни** — лише швидкі тести однієї функції чи класу, за секунду;
- **перед комітом і в CI** — усе, разом із застосунком, базою, Redis і HTTP.

## Зміна 1: дві папки { #folders }

```text title="tests/: крок 4 → крок 5"
tests/                              tests/
├── conftest.py                     ├── conftest.py        ← фікстура html(), маркер за папкою
├── test_models.py                  ├── factories.py       ← make_raw(**зміни)
├── test_parser.py                  ├── fixtures/          ← збережені сторінки *.html
├── test_api.py                     ├── unit/              ← без бази, Redis і мережі
├── test_crud.py                    │   ├── test_parser.py, test_models.py
└── test_redis.py                   │   ├── test_pipeline.py    ← парсер → модель
                                    │   └── test_scraper.py     ← мережа під моком
                                    └── integration/       ← застосунок цілком
                                        ├── conftest.py    ← client, aclient, тестова база
                                        ├── test_api.py, test_crud.py, test_redis.py
                                        ├── test_async_api.py       ← httpx.AsyncClient
                                        ├── test_db.py              ← справжній get_db
                                        └── test_scraper_server.py  ← локальний HTTP-сервер
```

`conftest.py` діє на свою папку і всі вкладені. Тому все про базу, Redis і `TestClient` переїхало в `tests/integration/conftest.py`: unit-тести цих фікстур не бачать і не можуть випадково підняти застосунок. У кореневому `tests/conftest.py` лишилось лише спільне: HTML-фікстури і маркери.

| Шар | Що перевіряє | Що справжнє | Приклади |
|---|---|---|---|
| unit | одну функцію чи клас | лише код, що тестується; мережа — мок | `test_parser.py`, `test_models.py`, `test_pipeline.py`, `test_scraper.py` |
| integration | кілька частин разом | застосунок, SQLite/PostgreSQL, fakeredis/Redis, aiohttp | `test_api.py`, `test_crud.py`, `test_db.py`, `test_scraper_server.py` |

## Зміна 2: маркер ставить папка { #marker-hook }

Можна писати `@pytest.mark.unit` над кожним тестом. Але про нього легко забути, а тест без маркера тихо випаде з `pytest -m unit`. Тому маркер ставить хук:

```python title="tests/conftest.py (фрагмент)"
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Маркер з назви папки: не треба пам'ятати про @pytest.mark.unit у кожному файлі."""
    for item in items:
        for layer in ("unit", "integration"):
            if f"{Path('tests') / layer}" in str(item.path):
                item.add_marker(getattr(pytest.mark, layer))
```

`pytest_collection_modifyitems` — **хук** pytest: функцію з цим ім'ям у `conftest.py` pytest викликає сам, коли вже зібрав усі тести, але ще не запустив жодного. `Path('tests') / layer` дає `tests/unit` на Linux і `tests\unit` на Windows, тому перевірка працює на обох системах.

Шлях одного тесту від збирання до запуску з `-m unit`:

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph S1 ["1. збирання: pytest знаходить тести"]
        direction LR
        C1["tests/unit/test_parser.py<br>test_containers_strategy"] ~~~ C2["tests/integration/test_api.py<br>test_health"]
    end
    subgraph S2 ["2. хук pytest_collection_modifyitems"]
        direction LR
        H1["'tests/unit' у шляху?"] -- так --> H2["add_marker(unit)"]
        H3["'tests/integration' у шляху?"] -- так --> H4["add_marker(integration)"]
    end
    subgraph S3 ["3. фільтр -m unit"]
        direction LR
        F1["test_containers_strategy<br>має unit"] ~~~ F2["test_health<br>немає unit"]
    end
    subgraph S4 ["4. запуск"]
        direction LR
        R1["виконано"] ~~~ R2["deselected"]
    end
    S1 --> S2 --> S3 --> S4

    class C1,C2 step
    class H1,H3 decision
    class H2,H4,F1 success
    class F2 warning
    class R1 success
    class R2 warning
```

## Зміна 3: маркери оголошено в `pytest.ini` { #pytest-ini }

```ini title="pytest.ini"
[pytest]
testpaths = tests
pythonpath = .
markers =
    unit: швидкі тести однієї функції чи класу — без бази, Redis і мережі
    integration: API разом з базою й Redis
asyncio_default_fixture_loop_scope = function
```

| Рядок | Що робить |
|---|---|
| `markers = …` | реєструє маркери; `pytest --markers` покаже їх з описом |
| `asyncio_default_fixture_loop_scope = function` | кожна async-фікстура (пакет `pytest-asyncio`) отримує свій цикл подій на тест — тести не ділять стан циклу |
| `pythonpath = .` | `from tests.factories import make_raw` працює з будь-якої папки запуску |

Без `markers` pytest не впаде, а попередить. Ось той самий прогін з видаленими рядками `markers`:

```text
tests/conftest.py:19: PytestUnknownMarkWarning: Unknown pytest.mark.unit - is this a typo?  You can register custom marks to avoid this warning - for details, see https://docs.pytest.org/en/stable/how-to/mark.html
tests/conftest.py:19: PytestUnknownMarkWarning: Unknown pytest.mark.integration - is this a typo?  ...
39 passed, 47 deselected, 2 warnings in 0.92s
```

## Результат { #result }

```text
$ pytest -q -p no:cacheprovider -m unit
.......................................                                  [100%]
39 passed, 47 deselected in 1.47s
$ pytest -q -p no:cacheprovider -m integration
...............................................                          [100%]
47 passed, 39 deselected in 5.02s
$ pytest -q -p no:cacheprovider
........................................................................ [ 83%]
..............                                                           [100%]
86 passed in 3.92s
```

Час залежить від машини. Співвідношення лишається: unit — секунда, integration — у кілька разів довше, бо кожен тест піднімає застосунок, базу і Redis.

| Файл | Тестів | Шар |
|---|---|---|
| `unit/test_models.py` | 22 | unit |
| `unit/test_parser.py` | 9 | unit |
| `unit/test_pipeline.py` | 2 | unit |
| `unit/test_scraper.py` | 6 | unit |
| `integration/test_api.py` | 17 | integration |
| `integration/test_crud.py` | 9 | integration |
| `integration/test_redis.py` | 9 | integration |
| `integration/test_async_api.py` | 3 | integration |
| `integration/test_db.py` | 4 | integration |
| `integration/test_scraper_server.py` | 5 | integration |
| **усього** | **86** | 39 + 47 |

`-m` приймає вираз: `-m "unit and not asyncio"` — лише синхронні unit-тести (33 passed, 53 deselected), `-m "not integration"` — те саме, що `-m unit`.

## Що справжнє, а що підмінене { #what-is-real }

Кожен шар відповідає на своє питання. Різниця між ними — в тому, що в тесті справжнє, а що підмінене:

```mermaid
flowchart LR
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph U ["unit: 39 тестів"]
        UP["parser, models<br>на fixtures/*.html"]
        US["fetch_one"] --> UM["Mock<br>ClientSession"]
    end
    subgraph I ["integration: 47 тестів"]
        TC["TestClient /<br>httpx.AsyncClient"] --> APP["FastAPI app<br>middleware, Depends"]
        APP --> DB["SQLite у пам'яті<br>або PostgreSQL"]
        APP --> RD["fakeredis<br>або Redis"]
        APP --> FS["скрапер-заглушка<br>dependency_overrides"]
        SC["scrape_all_async"] --> TS["TestServer<br>127.0.0.1"]
        GD["справжній get_db"] --> DB
    end

    class UP,US,TC,APP,SC,GD success
    class UM,FS warning
    class DB,RD,TS decision
```

- **зелене** — справжній код застосунку, який тест виконує;
- **жовте** — мок або заглушка: тест вирішує, що вона відповість;
- **синє** — фейк або справжній сервер: поводиться як реальний (SQL, команди Redis, HTTP), лише локально.

Як обрати підміну для конкретної залежності — схема в розділі [Фейк замість моку](fake_server.md#choose).

## Правило { #rule }

!!! tip "Правило"
    Шар тесту видно з його розташування: `tests/unit/` — без бази, Redis і мережі, `tests/integration/` — разом з ними. Маркер ставить папка, а не пам'ять автора тесту. Unit-тести запускай після кожної зміни, повний набір — перед комітом і в CI.

**Далі:** [Збережені сторінки замість рядків](html_fixtures.md) — HTML у файлах і тест конвеєра.
