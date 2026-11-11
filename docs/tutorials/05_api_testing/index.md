# Крок 5. Тестування API

> **Код кроку:** [`steps/05_api_testing`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/05_api_testing).
>
> **Передумови:** [Крок 4. Middleware, кеш і Redis](../04_middleware_redis/index.md): кеш і rate limit на Redis, фоновий збір, 41 тест (`TestClient`, SQLite у пам'яті, fakeredis).

## Де ми зараз { #where }

Після кроку 4 в агрегатора 41 зелений тест у п'яти файлах: `test_models.py`, `test_parser.py`, `test_api.py`, `test_crud.py`, `test_redis.py`. Здається, перевірено все. Але подивимось, чого ці тести **не** роблять:

- код, який ходить у мережу (`scraper.fetch_one`), не виконується жодного разу: API-тести підміняють скрапер заглушкою;
- справжній `get_db` теж не виконується: його підміняє тестова версія з `conftest.py`;
- парсер і модель перевірено окремо, кожен на своїх даних, а разом їх не запускав ніхто;
- звіт покриття показує 88%, і навіть ця цифра неточна.

## Проблема { #problem }

Зелені тести ще не означають робочого коду. Тести кроку 4 мовчать про чотири помилки, які вже є в коді:

| Помилка в коді кроків 1–4 | Хто її знайшов у кроці 5 |
|---|---|
| модель відхиляє кожну новину з `<time datetime="2024-05-08T10:30:00">` | тест конвеєра «парсер → модель» на збереженій сторінці |
| один невалідний байт UTF-8 на сторінці валить **увесь** збір | скрапер проти локального HTTP-сервера |
| `POST /api/scrape` приймає `https://fakerbc.ua/`: `endswith("rbc.ua")` | непокрита гілка у звіті покриття |
| парсер падає з `TypeError` на beautifulsoup4 4.12, яку дозволяє `requirements.txt` | прогін на мінімальних версіях залежностей |

У цьому кроці `news_hub` майже не змінюється ззовні. Змінюються його **тести**, а виправлення в коді — це чотири відповіді на чотири знахідки.

Як це перевірено: тести кроку 5 запущено на коді кроку 4 (`news_hub/` з кроку 4, `tests/` з кроку 5):

```text
$ pytest -q -p no:cacheprovider --continue-on-collection-errors
E   ImportError: cannot import name 'is_rbc_host' from 'news_hub.models'
E       assert 200 == 422
E       UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 1080: invalid start byte
E       AssertionError: assert [Rejected(raw...pected `:`'])] == []
FAILED tests/integration/test_api.py::test_bad_input_is_422[post-/api/scrape-kwargs4-pages]
FAILED tests/integration/test_scraper_server.py::test_undecodable_page_does_not_kill_scrape
FAILED tests/unit/test_pipeline.py::test_every_parsed_item_passes_the_model[demo_newsline-expected1]
ERROR tests/unit/test_models.py
3 failed, 61 passed, 1 error in 4.79s
```

Четверту помилку (beautifulsoup4 4.12) на свіжих версіях не видно взагалі. Її показує лише [прогін на мінімальних версіях](min_versions.md).

## Що додаємо { #what }

| Що | Де | Розділ |
|---|---|---|
| папки `unit/` і `integration/`, маркер з назви папки, `pytest -m unit` | `tests/conftest.py`, `pytest.ini` | [Шари тестів: unit і integration](test_layers.md) |
| HTML-фікстури, фабрика `make_raw`, тест конвеєра; виправлення `published_time` | `tests/fixtures/`, `tests/factories.py`, `tests/unit/test_pipeline.py` | [Збережені сторінки замість рядків](html_fixtures.md) |
| мок `aiohttp.ClientSession`, правило «patch where used» | `tests/unit/test_scraper.py` | [Мок мережі: patch where used](mock_network.md) |
| локальний HTTP-сервер з фікстурами; `errors="replace"`; межа fakeredis | `tests/integration/test_scraper_server.py`, `news_hub/scraper.py` | [Фейк замість моку: локальний HTTP-сервер](fake_server.md) |
| фікстура `aclient`, одночасні запити, rate limit під навантаженням | `tests/integration/conftest.py`, `test_async_api.py` | [API асинхронно: `httpx.AsyncClient`](async_client.md) |
| `.coveragerc`, покриття гілок, справжній `get_db`, `is_rbc_host` | `.coveragerc`, `tests/integration/test_db.py`, `news_hub/models.py` | [Покриття: що тести не зачепили](coverage.md) |
| прогін на найнижчих версіях з `requirements.txt`; виправлення `_classes` | `requirements.txt`, `news_hub/parser.py` | [Мінімальні версії залежностей](min_versions.md) |

## Архітектура: було → стало { #architecture }

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph OLD ["крок 4: 41 тест, 5 файлів поруч"]
        direction LR
        T0["test_models, test_parser<br>HTML рядками в тесті"] ~~~ A0["test_api, test_crud, test_redis<br>TestClient"]
        A0 --> F0["скрапер-заглушка<br>fetch_one не виконується"]
        A0 --> G0["копія get_db<br>оригінал не виконується"]
    end
    subgraph NEW ["крок 5: 86 тестів, 10 файлів у двох шарах"]
        direction LR
        U["unit: 39<br>парсер, модель, конвеєр"] --> FX["fixtures/*.html"]
        US["unit: fetch_one"] --> MK["Mock ClientSession"]
        I["integration: 47<br>TestClient і AsyncClient"] --> APP["FastAPI + SQLite<br>+ fakeredis"]
        SV["integration: scrape_all_async"] --> TS["TestServer<br>127.0.0.1"]
        GD["integration: справжній get_db"] --> APP
    end
    OLD --> NEW

    class T0,A0 step
    class F0,G0 error
    class U,US,I,SV,GD success
    class MK warning
    class FX,APP,TS decision
```

- **Два шари.** `tests/unit/` — одна функція чи клас без бази, Redis і мережі; `tests/integration/` — застосунок цілком або справжній HTTP-клієнт проти локального сервера. Маркер ставить папка, тож `pytest -m unit` займає секунду.
- **Справжнє, підмінене, фейк.** Зелене — код застосунку, який тест справді виконує. Жовте — мок: тест сам вирішує, що він відповість. Синє — фейк: поводиться як справжній ресурс (SQL, команди Redis, HTTP), але працює локально.
- **Нічого не видалено.** 41 тест кроку 4 переїхав у `unit/` та `integration/`; `test_crud.py` і `test_redis.py` не змінились ні на рядок.

## Файли кроку { #files }

| Файл | Що в ньому | Новий? |
|---|---|---|
| [`pytest.ini`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/pytest.ini) | маркери `unit` / `integration`, `asyncio_default_fixture_loop_scope` | змінено |
| [`.coveragerc`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/.coveragerc) | `branch = true`, `concurrency = thread,greenlet` | новий |
| [`requirements.txt`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/requirements.txt) | `+ pytest-asyncio>=0.24`, `+ pytest-cov>=5` | змінено |
| [`tests/conftest.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/conftest.py) | фікстура `html("…")`, маркер за папкою | змінено |
| [`tests/factories.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/factories.py) | `make_raw(**зміни)` — сира новина для тестів | новий |
| [`tests/fixtures/rbc_newsline_item.html`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/fixtures/rbc_newsline_item.html), [`demo_newsline.html`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/fixtures/demo_newsline.html) | збережені сторінки: справжній фрагмент rbc.ua і демо-розмітка | нові |
| [`tests/unit/test_models.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/unit/test_models.py), [`test_parser.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/unit/test_parser.py) | 22 і 9 тестів: модель і парсер на фікстурах | переїхали й доповнені |
| [`tests/unit/test_pipeline.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/unit/test_pipeline.py) | 2 тести: вихід парсера → модель | новий |
| [`tests/unit/test_scraper.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/unit/test_scraper.py) | 6 тестів: мережа під моком, «patch where used» | новий |
| [`tests/integration/conftest.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/integration/conftest.py) | `TestDatabase`, фікстури `client` і `aclient` | новий (з `tests/conftest.py` кроку 4) |
| [`tests/integration/test_api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/integration/test_api.py) | 17 тестів API (+ фільтри, `fakerbc.ua`, власні `pages`) | переїхав і доповнений |
| [`tests/integration/test_async_api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/integration/test_async_api.py) | 3 тести через `httpx.AsyncClient` | новий |
| [`tests/integration/test_db.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/integration/test_db.py) | 4 тести: справжній `get_db`, гілка PostgreSQL | новий |
| [`tests/integration/test_scraper_server.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/tests/integration/test_scraper_server.py) | 5 тестів: aiohttp проти `TestServer` | новий |
| `tests/integration/test_crud.py`, `test_redis.py` | по 9 тестів | переїхали без змін |
| [`news_hub/models.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/news_hub/models.py) | `is_rbc_host`, валідатор `time_from_iso_datetime` | змінено |
| [`news_hub/scraper.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/news_hub/scraper.py) | `resp.text(errors="replace")` | змінено |
| [`news_hub/parser.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/news_hub/parser.py) | `_classes` пропускає `None` | змінено |
| [`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/05_api_testing/news_hub/api.py) | `ScrapeRequest.only_rbc` → `is_rbc_host`, версія `0.5.0` | змінено |
| `news_hub/cache.py`, `db.py`, `jobs.py`, `middleware.py`, `repository.py`, `tables.py`, `snapshot.py` | з кроку 4 | без змін |

## Порядок читання { #reading-order }

1. [Шари тестів: unit і integration](test_layers.md) — нова структура `tests/` і маркери.
2. [Збережені сторінки замість рядків](html_fixtures.md) — фікстури, фабрика, тест конвеєра і перша знахідка.
3. [Мок мережі: patch where used](mock_network.md) — `fetch_one` без інтернету.
4. [Фейк замість моку: локальний HTTP-сервер](fake_server.md) — чого мок не бачить, друга знахідка, межа fakeredis.
5. [API асинхронно: `httpx.AsyncClient`](async_client.md) — тест і застосунок в одному циклі подій.
6. [Покриття: що тести не зачепили](coverage.md) — червоні рядки як питання, третя знахідка.
7. [Мінімальні версії залежностей](min_versions.md) — четверта знахідка.
8. [Контрольна точка](checkpoint.md) — перевірка, практика, самоперевірка.

Теорія до кроку — [Частина VII. Тестування API](../../07_testing/README.md). Загальна теорія тестування (піраміда, фікстури, mock і patch) — частина VIII [Django-книги](https://nikoriakviktor.github.io/notes_chat_app/08_testing_and_quality/).

## Запуск { #run }

З папки кроку `steps/05_api_testing`:

```bash
pip install -r requirements.txt
pytest -q                           # 86 passed
pytest -q -m unit                   # 39 passed, 47 deselected
pytest -q -m integration            # 47 passed, 39 deselected
pytest -q --cov=news_hub            # TOTAL 607 3 82 2 99% (налаштування — .coveragerc)
mypy --strict news_hub              # Success: no issues found in 12 source files
```

Ті самі тести на справжніх PostgreSQL 16 і Redis 7 (базу `news_hub_test` створи заздалегідь; Redis-база 15 очищується перед кожним тестом):

```bash
docker compose up -d db redis
TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test \
TEST_REDIS_URL=redis://localhost:6379/15 pytest -q          # 86 passed
```

Лише так ловиться гонка в rate limit: на fakeredis одночасних запитів не буває ([чому](fake_server.md#fakeredis-limit)).

Сервер запускається так само, як у кроці 4: `alembic upgrade head`, потім `uvicorn news_hub.api:app --reload` → http://127.0.0.1:8000/docs.

## Порівняння з кроком 4 { #diff }

```bash
git diff --no-index --stat steps/04_middleware_redis steps/05_api_testing
git diff --no-index steps/04_middleware_redis/news_hub steps/05_api_testing/news_hub
git diff --no-index steps/04_middleware_redis/tests steps/05_api_testing/tests
```

У закомічених файлах — 28 файлів, `726 insertions(+), 170 deletions(-)`. Якщо в папках кроків лишились `__pycache__/` після локального прогону, `--no-index` покаже й їх: він порівнює файли на диску, а не в git.

## Що далі { #next }

[Крок 6. AI-інструменти розробника](../06_ai_dev_tools/index.md): AI-агент додає друге джерело новин, і його код треба перевіряти так само, як свій, — навіть коли всі його тести зелені. Тести цього кроку — перший інструмент такої перевірки. А в кроці 7 з'явиться ще одна зовнішня межа — виклик LLM API, — і її мокатимемо за правилами цього кроку.
