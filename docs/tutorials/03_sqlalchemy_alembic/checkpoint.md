# Контрольна точка: крок 3

## Перевір, що крок робочий { #check }

З папки `steps/03_sqlalchemy_alembic`:

```text
$ pytest -q -p no:cacheprovider
................................                                         [100%]
32 passed in 1.34s
$ TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test pytest -q -p no:cacheprovider
................................                                         [100%]
32 passed in 4.86s
$ mypy --strict news_hub
Success: no issues found in 9 source files
```

Час залежить від машини. Тести на PostgreSQL перевірено з PostgreSQL 16 (`postgres:16-alpine`, той самий образ, що в `docker-compose.yml`).

Порівняно з кроком 2 додалось 9 тестів CRUD у `tests/test_crud.py`: `201` з `id` і виведеними полями, `409` на той самий `url`, `422` на неправильну новину, `404`, `PATCH` лише переданих полів і збереження змін, `204`, статистика з `GROUP BY`, «COMMIT не вдався → `500`», пошук без урахування регістру. У `tests/test_api.py` — ті самі 11 тестів, тепер на тестовій базі; перевірка OpenAPI знає нові шляхи.

## Чекліст { #checklist }

- [ ] `alembic upgrade head` створює таблицю; `alembic current` → `0001 (head)`; `alembic check` → `No new upgrade operations detected.`
- [ ] `POST /api/scrape` з `{"source": "snapshot"}` → `news_saved: 168`; удруге → `news_saved: 0`, `news_total: 168`.
- [ ] `POST /api/news` → `201` з `id`; той самий `url` удруге → `409`.
- [ ] `PATCH /api/news/{id}` з `{"category": "Економіка"}` змінює категорію й не чіпає заголовок; `GET` після цього показує нову категорію.
- [ ] `DELETE /api/news/{id}` → `204` без тіла; повторний `GET` → `404`.
- [ ] Після перезапуску uvicorn `GET /api/news/count` повертає те саме число.
- [ ] Можеш пояснити, чому на PostgreSQL нова новина після двох зборів отримує `id = 337`, а на SQLite — `169`.
- [ ] Можеш пояснити, що зміниться для клієнта, якщо прибрати `scope="function"`.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `500` на `/api/news`, у журналі `sqlite3.OperationalError: no such table: news` | не застосовано міграції; `lifespan` таблиць не створює | `alembic upgrade head` з тим самим `DATABASE_URL`, що в сервера |
| `FAILED: No 'script_location' key found in configuration.` | `alembic` запущено не з папки кроку — `alembic.ini` не знайдено | `cd steps/03_sqlalchemy_alembic` |
| `ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 5432)` | PostgreSQL не запущено або інший порт | `docker compose up -d db`, перевір `DATABASE_URL` |
| `alembic upgrade head` пройшов, а сервер «не бачить» новин | міграції й сервер дивляться в різні бази: `DATABASE_URL` задано лише в одному терміналі | задай `DATABASE_URL` в обох; без нього — файл `news_hub.db` у поточній папці |
| `OperationalError unknown function: now()` на першому `INSERT` у SQLite | автоміграція з `server_default=sa.text('now()')` | `sa.func.now()` — [міграції](alembic.md#autogenerate) |
| `ResponseValidationError` з `'loc': ('response', 'id')`, `'input': None` | об'єкт повернули до `flush()`: `INSERT` ще не було, `id` немає | `await session.flush()` після `add` — [сесія на запит](session_per_request.md#flush) |
| пошук кирилицею на SQLite не знаходить нічого | вбудований `lower()` SQLite не знає кирилиці | `make_engine` реєструє `_unicode_lower`; власний engine створюй через `make_engine` |
| у тесті `201`, хоча COMMIT «упав» | `Depends(get_db)` без `scope="function"` | `SessionDep` з `scope="function"` |

## Практика { #practice }

### Розібраний приклад: пошук `GET /api/news/search?q=` { #worked-example }

У кроці 2 пошук був завданням «спробуй самостійно» над словником. У першому прототипі агрегатора він виглядав так: `{"title": {"$regex": keyword, "$options": "i"}}` — рядок користувача ставав **регулярним виразом** у MongoDB. У кроці 3 пошук — SQL:

1. **Репозиторій.** Уся робота — в одному методі:

    ```python title="news_hub/repository.py (фрагмент)"
    async def search(self, q: str, limit: int = 20) -> list[NewsRow]:
        stmt = select(NewsRow).where(NewsRow.title.icontains(q, autoescape=True)).order_by(NewsRow.id).limit(limit)
        return list((await self._session.scalars(stmt)).all())
    ```

    `icontains` — «містить, без урахування регістру». `autoescape=True` — символи `%` і `_` у `q` шукаються буквально, а не як «будь-що». Який SQL це дає для `q="50%"`:

    ```text
    PostgreSQL: WHERE (news.title ILIKE '%%' || %(title_1)s::VARCHAR || '%%' ESCAPE '/') ORDER BY news.id
    параметри:  {'title_1': '50/%', 'param_1': 20}
    SQLite:     WHERE (lower(news.title) LIKE '%' || lower(?) || '%' ESCAPE '/') ORDER BY news.id
    ```

    `q` — параметр, а не частина SQL; `%` у ньому екрановано як `/%`. У SQLite `ILIKE` немає, тож SQLAlchemy будує `lower(...) LIKE lower(...)` — і тут потрібна підміна `lower()` з [розділу 1](engine_and_table.md#unicode-lower).

2. **Ендпоінт.** `q: str = Query(min_length=2, max_length=60)` — порожній чи надто довгий пошук відсічено до SQL (`422`).

3. **Порядок маршрутів.** `/api/news/search` оголошено **до** `/api/news/{news_id}`: інакше FastAPI спробував би прочитати `"search"` як `news_id: int` і відповів би `422`.

Результат на PostgreSQL зі знімком у базі (на SQLite — ті самі числа):

```python
for q in ("зеленськ", "ЗЕЛЕНСЬК", "%%"):
    found = api.get("/api/news/search", params={"q": q, "limit": 100}).json()
    print(repr(q), "→", len(found), [news["title"][:40] for news in found[:2]])
print(api.get("/api/news/search", params={"q": "а"}).status_code)
```

```text
'зеленськ' → 11 ['У Путіна образилися на дозвіл Зеленськог', 'Зеленський дозволив проведення параду в ']
'ЗЕЛЕНСЬК' → 11 ['У Путіна образилися на дозвіл Зеленськог', 'Зеленський дозволив проведення параду в ']
'%%' → 0 []
422
```

### Зміни приклад { #modify }

1. Додай до пошуку фільтр `lang: Literal["uk", "ru"] | None = Query(None)` — у репозиторії це ще одна умова `.where(NewsRow.lang == lang)`, як у `find`.
2. Додай у `NewsRepository` метод `latest(limit)` — найновіші за часом збору (`order_by(NewsRow.scraped_at.desc())`), і ендпоінт `GET /api/news/latest`. Не забудь про порядок маршрутів.

### Спробуй самостійно: міграція 0002 { #migration-0002 }

Підготуй таблицю до підсумків від LLM ([крок 7](../07_llm_api/index.md) зробить це по-своєму):

- у `NewsRow` — стовпець `summary: Mapped[str | None] = mapped_column(Text)`;
- `alembic revision --autogenerate --rev-id 0002 -m "news summary"` → **прочитай** файл міграції;
- `alembic upgrade head` на базі, де вже є новини; `alembic downgrade -1` і знову `upgrade head`;
- `summary` — у `NewsOut` і в `NewsPatch`.

**Критерії перевірки:** новини, зібрані до міграції, лишились на місці з `summary: null`; `PATCH {"summary": "…"}` зберігає підсумок; `alembic check` — `No new upgrade operations detected.`; тести проходять на SQLite і PostgreSQL.

Підказка: перш ніж створювати файл, запусти `alembic check` — він скаже, що моделі й база розійшлися (`FAILED: New upgrade operations detected: [('add_column', None, 'news', Column('summary', Text(), …))]`). На SQLite autogenerate загорне `add_column` у `with op.batch_alter_table('news') as batch_op:` — це `render_as_batch` з `env.py`.

### Знайди помилку 1: `PATCH` з `null` { #find-bug-patch }

Клієнт хоче «стерти» заголовок і надсилає:

```python
import httpx

base = "http://127.0.0.1:8000"
response = httpx.patch(f"{base}/api/news/1", json={"title": None})
print(response.status_code, repr(response.text))
print(httpx.get(f"{base}/api/news/1").json()["title"])
```

(Окремі виклики `httpx.patch`/`httpx.get`, а не один `httpx.Client`: після необробленого винятку uvicorn закриває з'єднання, і наступний запит через те саме з'єднання отримав би `httpx.ReadError: Connection reset by peer`.)

```text
500 'Internal Server Error'
Реформа ЗСУ
```

А `{"title": "Коротко"}` дає правильний `422`. Чому `null` — це `500`, а не `422`? Чи зіпсувалися дані? Як виправити, не ламаючи `PATCH {"category": …}` без заголовка?

??? success "Відповідь"

    `NewsPatch.title: str | None = Field(None, min_length=10, max_length=300)`. Тип **дозволяє** `None`, а `min_length` до `None` не застосовується — перевірка тіла проходить. `model_dump(exclude_unset=True)` відкидає лише поля, яких **немає** в тілі; явний `null` — передане поле, тож у циклі `setattr(row, "title", None)`. Далі `response_model=NewsOut` вимагає `title: str` — і падає вже **відповідь**:

    ```text
    fastapi.exceptions.ResponseValidationError: 1 validation error:
      {'type': 'string_type', 'loc': ('response', 'title'), 'msg': 'Input should be a valid string', 'input': None}
    ```

    Дані цілі: виняток стався до COMMIT, `get_db` зробив ROLLBACK (до того ж `title` у таблиці — `NOT NULL`). Але `500` каже клієнту «зламався сервер», хоча зламався запит.

    Одне з виправлень — валідатор, який забороняє `null` лише для **переданих** полів. Валідатори Pydantic за замовчуванням не запускаються для значень за замовчуванням, тож пропущене поле так і лишається «не передано»:

    ```python
    class NewsPatch(BaseModel):
        title: str | None = Field(None, min_length=10, max_length=300)
        category: str | None = Field(None, min_length=2, max_length=100)

        @field_validator("title", "category")
        @classmethod
        def not_null(cls, value: str | None) -> str:
            if value is None:
                raise ValueError("поле не може бути null; не хочеш міняти — не передавай його")
            return value
    ```

    Перевірено в копії кроку: усі 32 тести проходять, `mypy --strict` чистий, а

    ```text
    {'title': None} → 422 {'detail': [{'type': 'value_error', 'loc': ['body', 'title'], 'msg': 'Value error, поле не може бути null; не хочеш міняти — не передавай його', 'input': None, 'ctx': {'error': {}}}]}
    {'category': 'Економіка'} → 200 Економіка
    {} → 200 Економіка
    ```

    Додай і тест: `client.patch(f"/api/news/{id}", json={"title": None}).status_code == 422`.

### Знайди помилку 2: «перевір, потім встав» { #find-bug-race }

Студент вирішив, що `ON CONFLICT` — це складно, і написав збір «по-простому»: для кожної новини перевірити, чи є такий `url`, і лише тоді додати. Запускаємо **два збори одночасно** — як два користувачі натиснули «Зібрати» або бот і планувальник спрацювали разом:

```python
import asyncio

from sqlalchemy import delete, select

from news_hub.db import SessionFactory
from news_hub.models import validate_news
from news_hub.repository import news_values
from news_hub.snapshot import load_snapshot
from news_hub.tables import NewsRow

news, _ = validate_news(load_snapshot()[:20])


async def naive_add_many(items):
    async with SessionFactory() as session:
        saved = 0
        for item in items:
            exists = await session.scalar(select(NewsRow.id).where(NewsRow.url == str(item.url)))
            if exists is None:                     # «такого url ще немає — додаю»
                session.add(NewsRow(**news_values(item)))
                saved += 1
        await session.commit()
        return saved


async def two_scrapes_at_once():
    async with SessionFactory() as session:
        await session.execute(delete(NewsRow))
        await session.commit()
    results = await asyncio.gather(naive_add_many(news), naive_add_many(news), return_exceptions=True)
    for result in results:
        print(type(result).__name__, str(result).splitlines()[0].split(") ", 1)[-1])


asyncio.run(two_scrapes_at_once())
```

PostgreSQL:

```text
int 20
IntegrityError duplicate key value violates unique constraint "news_url_key"
```

SQLite:

```text
int 20
IntegrityError UNIQUE constraint failed: news.url
```

Кожен збір «перевірив» усі 20 `url`, і кожен вирішив, що новин немає. Чому, і що з цим робити?

??? success "Відповідь"

    **Гонка «перевір, потім зроби» (check-then-act).** Між `SELECT` і `COMMIT` є проміжок, і на кожному `await` цикл подій перемикається на інший збір. Обидва встигли виконати `SELECT` раніше, ніж хтось зробив `COMMIT`, тож обидва «побачили» порожню таблицю. Перший COMMIT пройшов, другий упав на `UNIQUE`: у справжньому ендпоінті це був би `500`.

    У тестах з одним користувачем цей код працює завжди — помилка проявляється лише під паралельними запитами. Найгірший вид помилок: у розробці її не видно.

    Виправлення — не перевіряти в Python, а **віддати рішення базі одним оператором**: `INSERT … ON CONFLICT (url) DO NOTHING` у `NewsRepository.add_many`. Ті самі два одночасні збори через `add_many`:

    ```text
    int 20
    int 0
    ```

    База перевіряє унікальність атомарно: кожна новина вставлена рівно один раз, ніхто не впав. Для одиничного `POST /api/news` — те саме правило з іншого боку: `UNIQUE` у таблиці + `IntegrityError` → `409`.

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| `DATABASE_URL` | діалект+драйвер://користувач:пароль@хост:порт/база; зі змінної середовища |
| `create_async_engine` | пул з'єднань; для PostgreSQL — `asyncpg`, для SQLite — `aiosqlite` |
| `Mapped` / `mapped_column` | таблиця як клас; `X \| None` — `NULL` дозволено |
| Pydantic vs SQLAlchemy модель | перевірка даних vs рядок таблиці; `from_attributes=True` з'єднує їх у відповіді |
| Сесія | робоче місце запиту: зміни → `flush` (SQL у транзакції) → `commit` |
| `get_db` + `scope="function"` | одна сесія й транзакція на запит, COMMIT до відповіді |
| Репозиторій | увесь SQL в одному місці; ендпоінти не знають, яка база |
| `ON CONFLICT DO NOTHING` | дублікати відсіює база атомарно; `id` при цьому можуть «перескакувати» |
| CRUD-коди | `201` створено, `404` немає, `409` конфлікт, `204` видалено без тіла |
| `exclude_unset=True` | `PATCH` змінює лише передані поля; явний `null` — теж «передане» |
| Alembic | версії схеми в git; autogenerate — чернетка, читай перед комітом |
| Check-then-act | «перевір, потім встав» ламається під паралельними запитами — правило даних віддай базі |

## Самоперевірка { #self-check }

1. Чим `NewsRow` відрізняється від `NewsItem` і чому не одна модель на все?
2. Навіщо `flush()` у `repo.create`, якщо COMMIT однаково буде в `get_db`?
3. Що станеться з клієнтом, якщо COMMIT не вдасться, з `scope="function"` і без нього (FastAPI ≥ 0.118)?
4. Чому `id` новин ідуть з дірками і чи це проблема?
5. Навіщо міграції, якщо є `Base.metadata.create_all()`? А навіщо тоді `create_all` у `conftest.py`?
6. Чому два одночасні `naive_add_many` зламались, а два `add_many` — ні?
7. Ендпоінт отримує і `RepoDep`, і `RowDep`. Скільки сесій відкриється на запит?

??? success "Відповіді"

    1. `NewsItem` перевіряє дані ззовні (довжина, домен, мова); `NewsRow` описує рядок таблиці (типи стовпців, `UNIQUE`, `id` і `scraped_at` від бази). У них різні задачі й різний час роботи; змішування тягне SQL у перевірку або правила перевірки в таблицю.
    2. Щоб `INSERT` пішов у базу зараз: помилка `UNIQUE` виникає в ендпоінті, де її перетворюють на `409`, а `id` і `scraped_at` уже є для відповіді. Без `flush` у відповіді `id: None` → `500` (перевірено: 5 тестів CRUD падають).
    3. З `scope="function"` — `500`: залежність завершується до відповіді. Без нього — клієнт уже отримав `200`/`201`, а дані не збережено (перевірено: `assert 201 == 500`).
    4. PostgreSQL бере значення лічильника до перевірки `UNIQUE`, і пропущені рядки його «з'їдають». Не проблема: `id` лише ідентифікує рядок; кількість — `count(*)`.
    5. `create_all` лише створює відсутні таблиці. Міграції змінюють наявну схему (додати стовпець, індекс) без втрати даних, у контрольованому порядку, з відкатом — і зберігаються в git. У тестах база щоразу порожня й тимчасова, тож `create_all` — найшвидший спосіб отримати ту саму схему.
    6. `naive_add_many` вирішує в Python між `SELECT` і `COMMIT` — інший збір встигає втрутитися. `add_many` робить один `INSERT … ON CONFLICT DO NOTHING`: унікальність перевіряє база атомарно.
    7. Одну: `get_db` — спільна залежність обох, і FastAPI кешує її результат у межах запиту. Тому «знайти» і «видалити» — одна транзакція.

## Що далі { #next }

[Крок 4. Middleware, кеш і Redis](../04_middleware_redis/index.md) — кеш `GET /api/news` перед репозиторієм, обмеження частоти запитів, фоновий збір.
