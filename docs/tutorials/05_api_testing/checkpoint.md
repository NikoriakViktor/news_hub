# Контрольна точка: крок 5

## Перевір, що крок робочий { #check }

З папки `steps/05_api_testing`:

```text
$ pytest -q -p no:cacheprovider
........................................................................ [ 83%]
..............                                                           [100%]
86 passed in 3.92s
$ pytest -q -p no:cacheprovider -m unit
.......................................                                  [100%]
39 passed, 47 deselected in 1.47s
$ pytest -q -p no:cacheprovider --cov=news_hub --cov-report=term:skip-covered
...
TOTAL                  607      3     82      2    99%
86 passed in 11.34s
$ mypy --strict news_hub
Success: no issues found in 12 source files
```

Порівняно з кроком 4: було 41 тест у п'яти файлах, стало 86 у десяти; покриття 88% (рядки, без greenlet) → 99% (рядки й гілки).

## Чекліст { #checklist }

- [ ] `pytest -m unit` проходить за секунди і не потребує ні бази, ні Redis, ні мережі.
- [ ] Можеш показати, де в `tests/` ставиться маркер `unit` / `integration`, і що буде, якщо прибрати `markers` з `pytest.ini`.
- [ ] `tests/unit/test_pipeline.py` бере сторінку з `tests/fixtures/` і перевіряє, що модель приймає все, що дав парсер.
- [ ] Можеш пояснити, чому `mock.patch("news_hub.parser.parse_rbc_news")` не діє на `fetch_one`.
- [ ] Можеш назвати, що виконує фейковий сервер і чого не виконує мок (декодування, заголовки, статус, тайм-аут).
- [ ] `test_concurrent_requests_hit_rate_limit_exactly` дає `[422]*5 + [429]*5`, і ти знаєш, чому на fakeredis він не доводить атомарність.
- [ ] Звіт покриття показує три непокриті рядки, і для кожного є пояснення.
- [ ] Знаєш, як прогнати тести на мінімальних версіях з `requirements.txt`.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `async def functions are not natively supported` | async-тест без `@pytest.mark.asyncio` (або не встановлено `pytest-asyncio`) | додай маркер (або `pytestmark = pytest.mark.asyncio` на модуль); `pip install -r requirements.txt` |
| `Expected 'parse_rbc_news' to be called once. Called 0 times.` | патч там, де функцію визначено (`news_hub.parser`), а не там, де її шукають | `mock.patch("news_hub.scraper.parse_rbc_news")` |
| `AttributeError: 'State' object has no attribute 'redis'` в async-тесті | `httpx.AsyncClient(transport=ASGITransport(app))` не запускає `lifespan` | `async with app.router.lifespan_context(app):` навколо клієнта — як у фікстурі `aclient` |
| `PytestUnknownMarkWarning: Unknown pytest.mark.unit` | маркер не оголошено в `pytest.ini` | рядки `markers = unit: … integration: …` |
| `pytest -m unitt` → `86 deselected`, жодного тесту | одруківка в імені маркера: вираз `-m` pytest не перевіряє, просто нічого не вибирає | дивись на рядок `… deselected`; список маркерів — `pytest --markers` |
| звіт покриття занижений: рядки сесії, `flush`, `commit` червоні, хоч тести бази зелені | coverage не стежить за greenlet, у яких async SQLAlchemy працює з базою | `concurrency = thread,greenlet` у `.coveragerc` |
| тест rate limit зелений, а на сервері під навантаженням ліміт пропускає більше запитів | на fakeredis гонки не буває | прогін з `TEST_REDIS_URL=redis://localhost:6379/15` |
| `FileNotFoundError: … tests/fixtures/demo_newsline.html.html` | фікстура `html` сама додає `.html`: `html("demo_newsline.html")` | без розширення: `html("demo_newsline")` |

## Практика { #practice }

### Розібраний приклад: тест ключа кешу { #worked-example }

`NewsCache.key` (крок 4) будує ключ з параметрів запиту. Що має бути правдою?

1. Той самий набір параметрів в **іншому порядку** — той самий ключ: `?lang=uk&limit=5` і `?limit=5&lang=uk` — один запит.
2. Інші параметри — інший ключ.
3. Після `invalidate()` ключ змінюється — старий кеш більше не читається.

Шар — unit: потрібен лише Redis, і fakeredis тут достатньо (гонок у тесті немає). Бази й застосунку тест не чіпає.

```python title="tests/unit/test_cache.py (розв'язок)"
import fakeredis
import pytest

from news_hub.cache import NewsCache


@pytest.mark.asyncio
async def test_key_depends_on_params_not_order_and_changes_after_invalidate() -> None:
    cache = NewsCache(fakeredis.FakeAsyncRedis(decode_responses=True))
    first = await cache.key("list", {"lang": "uk", "limit": 5})
    assert first == await cache.key("list", {"limit": 5, "lang": "uk"})
    assert first != await cache.key("list", {"lang": "ru", "limit": 5})
    await cache.invalidate()
    assert first != await cache.key("list", {"lang": "uk", "limit": 5})
```

```text
$ pytest -q -p no:cacheprovider tests/unit/test_cache.py
.                                                                        [100%]
1 passed in 0.29s
```

Перевір, що тест справді ловить помилку: прибери `sort_keys=True` у `NewsCache.key` — перший `assert` має впасти:

```text
>       assert first == await cache.key("list", {"limit": 5, "lang": "uk"})
E       AssertionError: assert 'news:v0:list:ec0101d00111' == 'news:v0:list:48061f7f2b99'
```

Тест, який не падає на зламаному коді, нічого не перевіряє. Тому «зламай код — подивись, що тест упав» — частина написання тесту.

### Зміни приклад { #modify }

1. Додай до тесту випадок з кирилицею в параметрах (`{"category": "Економіка"}`): ключ має складатися лише з ASCII, бо в ньому хеш, а не самі параметри.
2. Перепиши тест через `parametrize`: пари параметрів і очікування «ключі рівні / різні».

### Спробуй самостійно: фоновий збір проти фейкового сайту { #fake-site-job }

Напиши інтеграційний тест, у якому `POST /api/scrape/jobs` збирає новини з `TestServer`, а не із заглушки:

- підміни `get_scrapers` так, щоб `"async"` викликав справжній `scrape_all_async` з адресами фейкового сервера;
- але `ScrapeRequest` пропускає лише rbc.ua, тож адреси задай у самій підміні, а не в тілі запиту;
- тест — через `aclient` (тоді `TestServer` і застосунок в одному циклі подій); статус задачі опитуй через `GET /api/scrape/jobs/{job_id}`.

**Критерії перевірки:** статус задачі `done`, `news_saved == 1`, у базі — новина «США хочуть підкупити кубинців безплатним інтернетом, - AP»; тест проходить без інтернету; `pytest -m integration` зелений.

??? success "Підказка: каркас"

    ```python
    async with TestServer(site) as server:
        async def from_fake_site(pages: list[str] | None) -> ScrapeOutcome:
            return await scrape_all_async([str(server.make_url("/ukr/news/"))])

        app.dependency_overrides[get_scrapers] = lambda: {"async": from_fake_site, "sequential": from_fake_site}
        job = (await aclient.post("/api/scrape/jobs", json={})).json()
        ...   # опитуй статус, поки не "done" або "failed"
    ```

    Підміну встанови **після** того, як фікстура `aclient` вже поставила свою: `install()` записує заглушку в той самий ключ `get_scrapers`. Прибирає все `app.dependency_overrides.clear()` у кінці фікстури.

### Знайди помилку { #find-bug }

Ось два тести з кроків 1–4 (скорочено) і модель тих кроків (лише поле часу). Обидва тести зелені:

```python
from datetime import time
from pathlib import Path

from pydantic import BaseModel, ValidationError

from news_hub.parser import parse_rbc_news


class NewsTimeOld(BaseModel):                 # поле published_time моделі кроків 1–4
    published_time: time | None = None


def test_parser_reads_time_attribute() -> None:
    page = ('<div class="newsline__item"><a class="title" href="/ukr/news/1/">Уряд затвердив новий бюджет</a>'
            '<time datetime="2024-05-08T10:30:00">10:30</time></div>')
    assert parse_rbc_news(page)[0]["datetime"] == "2024-05-08T10:30:00"


def test_model_parses_time() -> None:
    assert NewsTimeOld(published_time="14:19").published_time == time(14, 19)


test_parser_reads_time_attribute()
test_model_parses_time()
print("обидва тести зелені")

raw = parse_rbc_news(Path("tests/fixtures/demo_newsline.html").read_text(encoding="utf-8"))
for item in raw:
    try:
        NewsTimeOld(published_time=item["datetime"])
    except ValidationError as error:
        print(f"{item['datetime']!r} → {error.errors()[0]['msg']}")
```

```text
обидва тести зелені
'2024-05-08T10:30:00' → Input should be in a valid time format, invalid time separator, expected `:`
'2024-05-08T09:15:00' → Input should be in a valid time format, invalid time separator, expected `:`
```

Кожен тест правильний. Чому разом вони пропустили помилку і який тест її ловить?

??? success "Відповідь"

    Кожен тест перевіряє свою половину **на своїх даних**: тест парсера — що він віддає ISO-рядок, тест моделі — що вона приймає «14:19». Ніхто не перевіряв **контракт між ними**: чи приймає модель те, що віддає парсер. Парсер віддає `"2024-05-08T10:30:00"`, а Pydantic для поля `time` приймає лише час — «Input should be in a valid time format». На сайті з контейнерами `newsline__item` модель відхиляла б **кожну** новину з атрибутом `<time datetime>`. `validate_news` не губить їх мовчки, а кладе в `rejected`, але звіт `POST /api/scrape` показував би «знайдено N, збережено 0».

    Ловить **тест конвеєра** (`tests/unit/test_pipeline.py`): вихід парсера на збереженій сторінці → модель, `rejected == []`. Правило: коли дві частини з'єднані даними, потрібен хоча б один тест, у якому дані з однієї справді йдуть у другу. Спільна фікстура (`demo_newsline.html`) для обох окремих тестів дала б те саме.

    Правильно — `field_validator("published_time", mode="before")` у `NewsItem`: з ISO-рядка береться час ([розбір](html_fixtures.md#fix)).

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| unit / integration | папки + маркери з `conftest.py`; `pytest -m unit` — секунди, після кожної зміни |
| `pytest_collection_modifyitems` | хук: змінює зібрані тести до запуску (тут — додає маркер за папкою) |
| Збережені сторінки | `tests/fixtures/*.html`: справжня розмітка, спільна для кількох тестів |
| Фабрика | `make_raw(**зміни)`: правильні значення за замовчуванням, у тесті видно лише важливе |
| Тест конвеєра | дані з однієї частини — справді в другу; ловить помилки контракту |
| Мок | лише зовнішня межа; patch **where used**; не бачить коду між запитом і рядком |
| Фейк | справжня поведінка локально: `TestServer`, SQLite, fakeredis; має свої межі (гонки) |
| `httpx.AsyncClient` + `ASGITransport` | тест і застосунок в одному циклі; `lifespan` запускаєш сам; `await` Redis напряму; `asyncio.gather` |
| Покриття | `concurrency = thread,greenlet` для async SQLAlchemy; `branch = true`; червоне — питання, а не мета |
| Мінімальні версії | те, що обіцяє `requirements.txt`, теж треба перевірити: `uv pip install --resolution lowest-direct` |

## Самоперевірка { #self-check }

1. Чим unit-тест відрізняється від інтеграційного в цьому проєкті? Назви по одному прикладу.
2. Навіщо маркер ставить хук у `conftest.py`, а не `@pytest.mark.unit` над кожним тестом?
3. Чому патч `news_hub.parser.parse_rbc_news` не впливає на `fetch_one`?
4. Яку помилку знайшов фейковий сервер і чому мок її не бачив?
5. Чому тест одночасних запитів на fakeredis не доводить атомарність rate limit?
6. Чому в `test_concurrent_requests_hit_rate_limit_exactly` відповіді `422`, а не `200`?
7. Що змінює `concurrency = thread,greenlet` у звіті покриття?
8. Навіщо тестувати справжній `get_db`, якщо API-тести працюють?
9. Чому `parser.py:110` не покрито, і чи треба це виправляти?

??? success "Відповіді"

    1. Unit — одна функція чи клас без бази, Redis і мережі: `test_parser.py`, `test_scraper.py` (мережа під моком). Integration — застосунок цілком або з реальним ресурсом: `test_crud.py` (API + база), `test_scraper_server.py` (справжній aiohttp + локальний сервер).
    2. Маркер з папки неможливо забути: тест у `tests/unit/` завжди має `unit`. Ручний маркер легко пропустити, і тест тихо випаде з `pytest -m unit`.
    3. `scraper.py` імпортував функцію до себе (`from .parser import …`), і `fetch_one` шукає ім'я в модулі `scraper`. Патч замінив ім'я лише в модулі `parser`.
    4. Сторінка з невалідним байтом UTF-8: `resp.text()` кидав `UnicodeDecodeError`, який `fetch_one` не ловив (це не `aiohttp.ClientError`), — і `gather` губив усі сторінки. У мока `text()` повертає готовий рядок, декодування не відбувається.
    5. fakeredis не віддає керування циклу подій між командами — одночасні корутини не перемежовуються, гонки не буває. «Наївний» лічильник на ньому теж проходить. Доводить лише прогін зі справжнім Redis: там наївний лічильник дав `[422]*10`.
    6. Тіло `{"source": "ftp"}` навмисно неправильне. `422` показує, що запит дійшов до перевірки тіла, тобто rate limit його вже порахував. Ліміт рахує й помилкові запити, інакше ними можна засипати сервер.
    7. coverage починає бачити рядки, виконані в greenlet, — так async SQLAlchemy працює з базою. Без цього звіт занижений: на тестах кроку 4 — 70 непокритих рядків замість 54 (88% замість 91%).
    8. API-тести підміняють `get_db` копією з `conftest.py`, тож оригінал не виконується ніколи. Копія може розійтися з оригіналом (наприклад, загубити `rollback`), а тести лишаться зеленими.
    9. Це `if not isinstance(a, Tag): continue` — перевірка для mypy: `find_all("a", href=True)` повертає лише `Tag`, тож на справжніх даних гілка не виконується. Виправляти не треба: рядок непокритий свідомо, і причина відома.

## Що далі { #next }

[Крок 6. AI-інструменти розробника](../06_ai_dev_tools/index.md) — AI-агент додає в проєкт друге джерело новин, а ми перевіряємо написаний ним код, навіть коли всі його тести зелені. Тести цього кроку — перший інструмент такої перевірки.
