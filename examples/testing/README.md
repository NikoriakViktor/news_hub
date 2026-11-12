# Тестування API: приклад до Частини VII

Невеликий застосунок новин `newsapp` (FastAPI + SQLAlchemy) і його тести. На ньому показано все, про що
Частина VII книги: основи pytest, фікстури, підміни, тести FastAPI, тести з базою, покриття й мутації.

```bash
pip install -r requirements.txt
pytest -q                     # 68 passed, 1 skipped, 1 deselected
pytest -q -m slow             # довгий тест, який addopts за замовчуванням пропускає
pytest -q -n 2                # паралельно (pytest-xdist)
pytest -q --cov=newsapp --cov-branch --cov-report=term-missing
uvicorn newsapp.api:app --reload          # сам застосунок: http://127.0.0.1:8000/docs
```

Ті самі тести на PostgreSQL (skip зникає — `test_too_long_source_is_rejected_by_database` виконується):

```bash
docker run -d --name testing-pg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -p 5432:5432 postgres:16-alpine
pip install "psycopg[binary]>=3.1"
TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:5432/test pytest -q       # 69 passed, 1 deselected
TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:5432/test pytest -q -n 2  # кожен воркер — своя схема
docker rm -f testing-pg
```

## Що де

| Файл | Що показує | Сторінка книги |
|---|---|---|
| `newsapp/text.py` | чисті функції: `reading_time`, `slugify`, `shorten` | Основи pytest |
| `newsapp/mail.py`, `digest.py`, `alerts.py` | зовнішня межа (SMTP): параметром і через імпорт | Підміни |
| `newsapp/storage.py` | таблиця, репозиторій, рецепт SAVEPOINT і `lower()` для SQLite | Тести з базою даних |
| `newsapp/api.py` | lifespan, `get_db`, middleware `X-Request-ID`, 404/409/422/500 | Тестування FastAPI |
| `tests/conftest.py` | транзакція на тест, `client`, фабрика `make_article`, схема на воркер | Фікстури, Тести з базою |
| `tests/test_text.py`, `test_unittest_style.py` | `assert`, межі, `raises`, `approx`, `parametrize`, маркер `slow` | Основи pytest |
| `tests/test_fixtures.py` | scope, `yield`, `tmp_path`, `monkeypatch`, `capsys` | Фікстури |
| `tests/test_doubles.py`, `fakes.py` | dummy, stub, mock, spy, fake, `patch`, `autospec` | Підміни |
| `tests/test_api.py`, `test_async_api.py` | `TestClient`, `dependency_overrides`, `httpx.AsyncClient` | Тестування FastAPI |
| `tests/test_db.py` | відкат, обмеження бази, `@pytest.mark.postgres` | Тести з базою даних |
| `tests/test_properties.py` | Hypothesis: властивості `shorten` і `slugify` | Якість тестів |

## `demos/` — навмисно червоне

`pytest` збирає лише `tests/` (`testpaths` у `pytest.ini`). У `demos/` — приклади помилок, кожен запускається
окремо, наприклад `pytest demos/test_failures.py`:

| Файл | Що падає і чому |
|---|---|
| `test_failures.py` | як pytest показує різницю словників і списків, `DID NOT RAISE`, `0.1 + 0.2` |
| `test_scope_leak.py` | змінюваний об'єкт у фікстурі `scope="module"` |
| `test_wrong_patch.py` | патч там, де функцію визначено, — справжній SMTP |
| `test_client_pitfalls.py` | `TestClient` без `with`, `raise_server_exceptions`, `ASGITransport` без lifespan |
| `test_typo_marker.py` | одруківка в маркері з `--strict-markers` |
| `test_ai_shorten.py` + `ai_shorten.py` | код від AI: «його» тест зелений, властивості — ні |
| `test_pages.py` + `pages.py` | покриття рядків 100%, гілок — ні |
| `test_no_asserts.py` | 100% покриття без жодної перевірки |
| `sqlite_vs_postgres.py` | `python demos/sqlite_vs_postgres.py [URL PostgreSQL]` — що SQLite пропускає |

## Мутаційне тестування (необов'язково)

```bash
pip install mutmut
mutmut run            # налаштування — setup.cfg; копія коду — у mutants/ (у .gitignore)
mutmut results        # survived — мутант, якого не помітив жоден тест
mutmut show newsapp.text.x_shorten__mutmut_3
```

Розбір — у книзі, Частина VII. Тестування API.
