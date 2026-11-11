# Контрольна точка: крок 4

## Перевір, що крок робочий { #check }

З папки `steps/04_middleware_redis`:

```text
$ pytest -q -p no:cacheprovider
.........................................                                [100%]
41 passed in 2.41s
$ mypy --strict news_hub
Success: no issues found in 12 source files
```

Порівняно з кроком 3 (32 тести) додалось 9 тестів у `tests/test_redis.py`:

| Тест | Що перевіряє |
|---|---|
| `test_cache_miss_then_hit` | `MISS`, потім `HIT` з тим самим JSON; інші параметри — `MISS` |
| `test_write_invalidates_cache` | після `POST /api/news` статистика — `MISS` і `total == 169` |
| `test_failed_write_keeps_cache` | `409` кеш не скидає — далі `HIT` |
| `test_request_id_and_timing_headers` | свій `X-Request-ID` повертається, без нього — згенерований з 8 символів; `X-Process-Time` закінчується на `ms` |
| `test_rate_limit_429_with_retry_after` | 5 × `200`, далі `429`; `0 < Retry-After <= 60`; `GET` не обмежується |
| `test_rate_limit_key_without_ttl_heals` | ключ ліміту без TTL отримує TTL (зі старою логікою «`EXPIRE` при `count == 1`» тест падає) |
| `test_background_job_done` | `202` + `queued`, потім `done`, 168 знайдено й збережено |
| `test_background_job_failure_is_recorded` | скрапер падає → `failed` з текстом помилки |
| `test_job_invalidates_cache_and_unknown_job_404` | після фонового збору статистика не застаріла; невідома задача — `404` |

Redis у тестах — `fakeredis`. На справжньому Redis 7 (`TEST_REDIS_URL=redis://localhost:6379/15 pytest`) — теж `41 passed`.

## Чекліст { #checklist }

- [ ] `docker compose up -d redis` і `uvicorn news_hub.api:app --reload` запускаються; у консолі є рядки `INFO news_hub: <id> GET … → 200 … ms`.
- [ ] Кожна відповідь має `X-Request-ID` і `X-Process-Time`; свій `X-Request-ID` повертається без змін.
- [ ] `GET /api/news?lang=uk&limit=3` двічі поспіль: `X-Cache: MISS`, потім `HIT`.
- [ ] `POST /api/news` (`201`) скидає кеш, повторний з тим самим `url` (`409`) — ні.
- [ ] Шостий `POST /api/scrape` за хвилину → `429` з `Retry-After` і `X-RateLimit-Remaining: 0`.
- [ ] `POST /api/scrape/jobs` → `202` з `job_id`; `GET /api/scrape/jobs/{job_id}` → `done`; `GET /api/scrape/jobs/nope` → `404`.
- [ ] Колекція Postman проходить: 16 запитів, 25 перевірок.
- [ ] Можеш пояснити, чому версію кешу збільшує middleware, а не ендпоінт.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `/health` → `200`, а `GET /api/news` → `500`; у консолі `redis.exceptions.ConnectionError: Error 111 connecting to localhost:6379` | Redis не запущений: клієнт підключається лише з першою командою, тому старт і `/health` проходять | `docker compose up -d redis` або `REDIS_URL=fakeredis://` для пробного запуску |
| `429` у Swagger після кількох експериментів | вичерпано 5 зборів за 60 с з твоєї адреси | дочекайся `Retry-After` секунд або видали ключ: `redis-cli DEL rate:scrape:127.0.0.1` |
| змінив новину напряму в базі (SQL-клієнт), а API ще хвилину показує стару | кеш не знає про записи в обхід API | дочекайся TTL (60 с) або `redis-cli INCR news:version` |
| `X-Cache` у відповіді немає | відповідь — помилка (`422`) або інший ендпоінт: кешуються лише `GET /api/news` і `/api/news/stats` | дивись статус і шлях |
| у тестах статус задачі одразу `done`, а на сервері — `queued`/`running` | `TestClient` чекає на фонові задачі, сервер — ні | на сервері опитуй статус, поки `queued`/`running` |
| рядків `news_hub` у журналі немає | новий обробник журналу додає `setup_logging()` у `lifespan`; без `lifespan` (свій скрипт без `with TestClient`) його нема | `with TestClient(app)` або `logging.basicConfig(level=logging.INFO)` |

## Практика { #practice }

### Розібраний приклад: кеш для `GET /api/news/{news_id}` { #worked-example }

Задача: картку новини відкривають частіше, ніж стрічку. Закешувати і її.

1. **Ключ** — `await cache.key("item", {"id": news_id})`. Версія спільна з усім кешем новин, тож будь-який запис (зокрема `PATCH` цієї новини) скидає й картки.
2. **Hit** — `cached_json(cached, "HIT")`.
3. **Miss** — прочитати з репозиторію; **немає — `404`, і `404` не кешуємо**: інакше новина, створена за секунду, 60 секунд виглядала б відсутньою.
4. **Запис** — `NewsOut.model_validate(row).model_dump_json()` → `cache.set`.

```python title="news_hub/api.py (розв'язок)"
@app.get("/api/news/{news_id}", response_model=NewsOut, tags=["news"], summary="Одна новина")
async def get_news(news_id: int, repo: RepoDep, cache: CacheDep) -> Response:
    key = await cache.key("item", {"id": news_id})
    if (cached := await cache.get(key)) is not None:
        return cached_json(cached, "HIT")
    row = await repo.get(news_id)
    if row is None:
        raise HTTPException(404, detail=f"новини {news_id} немає")
    payload = NewsOut.model_validate(row).model_dump_json()
    await cache.set(key, payload)
    return cached_json(payload, "MISS")
```

`RowDep` (залежність `get_news_or_404` з кроку 3) тут не підходить: він читає базу **до** перевірки кешу, і кеш нічого б не зекономив.

Перевірка через `TestClient` (новина створена, потім `PATCH` категорії, потім неіснуючий id):

```python
with TestClient(app) as client:
    news_id = client.post("/api/news", json={"title": "НБУ залишив облікову ставку без змін",
                                             "url": "https://www.rbc.ua/ukr/news/nbu-rate-778.html"}).json()["id"]
    for _ in range(2):
        r = client.get(f"/api/news/{news_id}")
        print(r.status_code, r.headers.get("X-Cache"), r.json()["category"])
    client.patch(f"/api/news/{news_id}", json={"category": "Економіка"})
    r = client.get(f"/api/news/{news_id}")
    print("після PATCH:", r.status_code, r.headers.get("X-Cache"), r.json()["category"])
    for _ in range(2):
        r = client.get(f"/api/news/{news_id + 1}")
        print(r.status_code, r.headers.get("X-Cache"), r.json())
```

```text
200 MISS Новини
200 HIT Новини
після PATCH: 200 MISS Економіка
404 None {'detail': 'новини 2 немає'}
404 None {'detail': 'новини 2 немає'}
```

`PATCH` пройшов через `invalidate_cache` (шлях `/api/news/…`, статус `200`) — картка перечитана з бази. `404` не має `X-Cache`: його не кешували.

### Зміни приклад { #modify }

1. Зроби TTL налаштовуваним: `NEWS_CACHE_TTL` зі змінної середовища, за замовчуванням 60. Перевір через `redis-cli TTL <ключ>`, що значення застосувалось.
2. Додай ліміт для `POST /api/news`: 30 за хвилину, дія `"create"` — окремий лічильник від `"scrape"`. Тест: 31-й запит — `429`, а `POST /api/scrape` при цьому ще проходить.

### Спробуй самостійно: ковзне вікно { #try-yourself }

Напиши `SlidingRateLimiter.hit(client, action)` на **sorted set** Redis (множина, де кожен елемент має числовий бал і їх можна вибирати за діапазоном балів):

- ключ `rate:sliding:<action>:<client>`, елемент — унікальний id запиту, бал — час у мілісекундах;
- в одній транзакції: `ZREMRANGEBYSCORE` (прибрати старші за `now - window`), `ZADD` (додати поточний), `ZCARD` (скільки у вікні), `PEXPIRE` (ключ зникне, коли все застаріє);
- дозволено, якщо `ZCARD <= limit`.

**Критерії перевірки:** демонстрація [«межі вікна»](rate_limit.md#fixed-window) пропускає не більше 3 запитів за будь-які 2 секунди; тест з `fakeredis`; `mypy --strict` чистий.

Подумай: відхилений запит теж лишається в множині — чи це те, що тобі потрібно? Що буде з клієнтом, який шле запити безперервно?

### Знайди помилку { #find-bug }

Колега вирішив, що окрема `session_factory` для фону — зайве ускладнення, і передав у задачу **репозиторій запиту**:

```python
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from news_hub.api import JobStore, RedisDep, RepoDep, app
from news_hub.models import validate_news
from news_hub.repository import NewsRepository
from news_hub.snapshot import load_snapshot


async def scrape_in_background(repo: NewsRepository, jobs: JobStore, job_id: str) -> None:
    valid, _ = validate_news(load_snapshot())
    saved = await repo.add_many(valid)
    await jobs.update(job_id, status="done", news_saved=saved)


@app.post("/api/scrape/jobs-buggy", status_code=202)
async def start_buggy(background: BackgroundTasks, repo: RepoDep, redis: RedisDep) -> dict[str, str]:
    job = await JobStore(redis).create("snapshot", "async")
    background.add_task(scrape_in_background, repo, JobStore(redis), job.job_id)
    return {"job_id": job.job_id}


with TestClient(app) as client:
    client.delete("/api/news")
    job_id = client.post("/api/scrape/jobs-buggy").json()["job_id"]
    job = client.get(f"/api/scrape/jobs/{job_id}").json()
    print("задача:", {key: job[key] for key in ("status", "news_saved")})
    print("у базі:", client.get("/api/news/count").json())
```

```text
задача: {'status': 'done', 'news_saved': 168}
у базі: {'count': 0}
```

А серед повідомлень у консолі — попередження SQLAlchemy:

```text
/usr/lib/python3.12/weakref.py:590: SAWarning: The garbage collector is trying to clean up non-checked-in connection <AdaptedConnection <aiosqlite.core.Connection object at 0x732f1b0ef2c0>>, which will be terminated.  Please ensure that SQLAlchemy pooled connections are returned to the pool explicitly, either by calling ``close()`` or by using appropriate context managers to manage their lifecycle.
```

Задача звітує «збережено 168», а в базі порожньо. Чому, і чому це найгірший вид помилки?

??? success "Відповідь"

    Фонова задача виконується **після** відповіді. На той момент `get_db` уже зробив COMMIT своєї транзакції й закрив сесію. Але `AsyncSession` після закриття можна використати знову: вона тихо бере з пулу з'єднання й відкриває **нову** транзакцію. `INSERT` виконується, `RETURNING` повертає 168 id… а COMMIT цієї нової транзакції ніхто не робить — `get_db` уже завершився. З'єднання висить з відкритою транзакцією, поки збирач сміття не прибере сесію (звідси `SAWarning`), і тоді транзакція відкочується. Поки вона висить, у PostgreSQL це «idle in transaction» з блокуваннями рядків, у SQLite — блокування бази на запис.

    Найгірший вид помилки: **жодного винятку**, статус `done`, `news_saved: 168` — а даних немає. Помилку побачать лише користувачі, коли стрічка лишиться порожньою.

    Виправлення — як у `run_scrape_job`: задача створює **свою** сесію (`async with session_factory() as session`) і сама робить `await session.commit()`. Правило: фонова задача не бере із запиту нічого з часом життя запиту — сесію бази, відкриті файли, об'єкт `Request`. Незмінні дані (id, параметри, JSON) передавати можна.

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| Middleware | код до й після кожного запиту; `call_next` — далі по ланцюгу; можна не викликати й відповісти самому |
| Порядок middleware | останній зареєстрований — зовнішній; запит — всередину, відповідь — назовні |
| `X-Request-ID`, `X-Process-Time` | позначка запиту й час обробки — для журналу й пошуку проблем |
| Cache-aside в API | ключ з параметрів запиту; у кеші — готовий JSON; TTL; `X-Cache: HIT/MISS` |
| Версія кешу | `INCR news:version` замість видалення ключів за шаблоном; збільшувати **після COMMIT** успішного запису |
| `KEYS` | перебирає всю базу й блокує Redis — не в коді застосунку |
| Rate limit | `INCR` + `EXPIRE … NX` однією транзакцією; `429`, `Retry-After`, `X-RateLimit-*` |
| Фіксоване vs ковзне вікно | фіксоване — простіше, на межі пропускає до 2× ліміту; ковзне — точніше, sorted set |
| `202 Accepted` + `BackgroundTasks` | відповісти одразу, працювати після відповіді; статус — polling |
| Фонова задача | своя сесія бази й свій COMMIT; помилку — у статус; зникає з перезапуском процесу |
| Redis vs база | у Redis — те, що можна втратити (кеш, ліміти, статуси); дані — в базі |

## Самоперевірка { #self-check }

1. У якому порядку виконаються три middleware з `api.py` для запиту і для відповіді?
2. Чому в кеші зберігаємо готовий JSON, а не об'єкти `NewsRow`?
3. Чому версію кешу збільшує middleware, а не ендпоінт?
4. Чому `POST /api/news` з відповіддю `409` не скидає кеш, і чому це правильно?
5. Що станеться з rate limit, якщо `INCR` і `EXPIRE` — окремі команди, а процес упаде між ними?
6. Скільки запитів може пройти фіксоване вікно «3 за 2 с» за пів секунди на межі вікон?
7. Чому `202`, а не `200`, і де клієнт бачить результат?
8. Чому фонова задача не може використати сесію бази з запиту?

??? success "Відповіді"

    1. Запит: `request_context` → `rate_limit` → `invalidate_cache` → ендпоінт. Відповідь — навпаки: `invalidate_cache` → `rate_limit` → `request_context`. Останній зареєстрований — зовнішній.
    2. Redis зберігає рядки; об'єкти SQLAlchemy прив'язані до сесії й не серіалізуються. Готовий JSON при hit віддаємо як є — ні бази, ні Pydantic.
    3. COMMIT робить `get_db` після ендпоінта. Версія, збільшена до COMMIT, дає паралельному `GET` закешувати старі дані під новою версією на 60 с. Middleware бачить відповідь уже після COMMIT.
    4. `invalidate_cache` скидає кеш лише при `status_code < 400`. `409` означає, що запису не було — дані в базі ті самі, і скидати кеш означало б зайві запити до бази.
    5. Ключ лишиться без TTL (`TTL = -1`), `count == 1` більше не трапиться — клієнта заблоковано назавжди. `EXPIRE … NX` у тій самій транзакції ставить TTL навіть такому «залишку».
    6. До 5: залишок старого вікна (2) + нове вікно (3). Саме стільки й виміряли.
    7. `202 Accepted` — «прийнято до роботи», а не «готово»: результату ще немає. Клієнт отримує `job_id` і опитує `GET /api/scrape/jobs/{job_id}`, поки статус не стане `done` чи `failed`.
    8. Задача виконується після відповіді, коли `get_db` уже зробив COMMIT і закрив сесію. Записи у «воскреслій» сесії ніхто не закомітить — дані тихо пропадуть, а статус буде `done`.

## Що далі { #next }

[Крок 5. Тестування API](../05_api_testing/index.md) — тести розділяться на unit та integration, мережу підмінять мок і фейковий HTTP-сервер, API перевірятимуть асинхронно через `httpx`, а покриття покаже, що тести не зачепили.
