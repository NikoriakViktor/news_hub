# Лаба 3. Кеш пошуку й інвалідація без холостих скидань { #lab-03 }

| | |
|---|---|
| Основа | [крок 4](../tutorials/04_middleware_redis/index.md) — `steps/04_middleware_redis` |
| Що тренує | cache-aside для нового ендпоінта, нормалізація ключа, зв'язок ендпоінт → middleware через `request.state`, інвалідація у фоновій задачі, тести кешу через версію в Redis |
| Складність | ★★☆ |
| Орієнтовний час | 2–3 години |

## Мета { #goal }

**Задача.** У кроці 4 кеш скидається **версією**: будь-який успішний запис у новини робить `INCR news:version`,
і всі ключі кешу стають непотрібними ([Інвалідація: версія кешу](../tutorials/04_middleware_redis/cache.md#invalidation)).
Правило просте й безпечне, але воно не питає, чи запис **справді щось змінив**. Перевірка на копії кроку 4
(SQLite у пам'яті + fakeredis, як у тестах кроку):

```text
scrape 1: 168 version 1                    ← зібрали 168 новин — кеш скинуто, правильно
scrape 2: 0 version 2                      ← той самий знімок, нових 0 — кеш однаково скинуто
stats after GET: HIT
stats after 3rd scrape (0 saved): MISS     ← нічого не змінилось, а статистику рахуємо заново
search X-Cache: None 11                    ← пошук не кешується взагалі
delete on empty: {'deleted': 0} version 4 -> 5
job: 1 version 6
job: 0 version 7                           ← фоновий збір без нових новин — теж скидає
```

Збір за розкладом (або кнопка «Зібрати», яку тиснуть щохвилини) здебільшого не знаходить нічого нового. Кожен такий
збір обнуляє кеш для **всіх** читачів: наступні запити стрічки й статистики йдуть у базу. Кеш, який скидають
частіше, ніж він встигає допомогти, — це лише зайвий запит до Redis.

Друга половина задачі — пошук. У кроці 4 `/api/news/search` свідомо не кешували: довільний `q` — стільки ж ключів,
скільки запитів ([Що кешувати, а що ні](../tutorials/04_middleware_redis/cache.md#what-to-cache)). Тепер стрічка
стабільна, а пошук — найдорожчий запит (`LIKE '%…%'` без індексу). Переглянь це рішення: ключі живуть лише `TTL`
секунд, тож їх у Redis не більше, ніж різних пошуків за 60 секунд; а нормалізований ключ (`q.lower()`) робить
«Зеленськ», «зеленськ» і «ЗЕЛЕНСЬК» одним ключем — пошук однаково не розрізняє регістр.

**Зміна.**

1. `GET /api/news/search` — cache-aside з ключем `("search", {"q": q.lower(), "limit": limit})` і заголовком `X-Cache`.
2. Ендпоінт, який знає, що нічого не змінив, каже про це middleware: `request.state.news_changed = False`.
   `invalidate_cache` пропускає `INCR`, якщо прапорець `False`. Ендпоінт, що нічого не сказав, як і раніше
   скидає кеш — безпечне значення за замовчуванням.
3. Фоновий збір `run_scrape_job` скидає кеш лише тоді, коли `saved > 0`.

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph S1["1. ендпоінт POST /api/scrape"]
        direction LR
        A1["add_many → saved = 0"] --> A2["request.state<br>news_changed = False"]
    end
    subgraph S2["2. get_db"]
        direction LR
        B1["COMMIT"]
    end
    subgraph S3["3. invalidate_cache"]
        direction LR
        C1{"запис, статус < 400<br>і news_changed?"}
        C1 -->|так| C2["INCR news:version"]
        C1 -->|ні| C3["версія та сама:<br>кеш живий"]
    end
    S1 --> S2 --> S3

    class A1,B1 step
    class A2 warning
    class C1 decision
    class C2 step
    class C3 success
```

**Результат.** Збір без нових новин, `DELETE /api/news` на порожній таблиці й фоновий збір без нових новин не
чіпають версію кешу — наступний `GET` дає `HIT`. Справжній запис скидає кеш, як і раніше. Повторний пошук не йде в
базу.

**Правило.** Інвалідуй, коли змінились **дані**, а не коли прийшов запит з методом запису. Знання «чи змінилось»
є лише в ендпоінті, а момент «після COMMIT» — лише в middleware: передай перше другому через `request.state`, а
безпечним значенням за замовчуванням залиш «змінилось».

## Звідки починаємо { #start }

```bash
cp -r steps/04_middleware_redis lab_03 && cd lab_03
pip install -r requirements.txt
pytest -q
```

```text
41 passed in 1.81s
```

Тести кроку 4 не потребують ні PostgreSQL, ні Redis: SQLite у пам'яті й fakeredis
([`tests/conftest.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/tests/conftest.py)).
Код, який змінюватимеш:
[`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/news_hub/api.py),
[`news_hub/middleware.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/news_hub/middleware.py)
(`invalidate_cache`),
[`news_hub/jobs.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/04_middleware_redis/news_hub/jobs.py)
(`run_scrape_job`).

## Вимоги { #requirements }

1. **Кеш пошуку.** `GET /api/news/search` віддає `X-Cache: MISS`, а повторний такий самий запит — `X-Cache: HIT`
   з тим самим тілом. Ключ:
    - не залежить від регістру `q` (`"Зеленськ"` і `"ЗЕЛЕНСЬК"` — один ключ);
    - залежить від `limit` (`limit=5` і `limit=6` — різні ключі);
    - містить версію кешу — новий запис у новини робить пошук знову `MISS`, і в результаті вже є нова новина.
2. Перевірки `q` (2–60 символів) лишаються: `?q=а` → `422`. Помилки не кешуються.
3. **`POST /api/scrape`**, який зберіг 0 новин, не змінює `news:version`.
4. **`DELETE /api/news`**, який видалив 0 новин, не змінює `news:version`.
5. **Фоновий збір** (`POST /api/scrape/jobs`), що зберіг 0 новин, не змінює `news:version`.
6. Усе, що змінює дані, скидає кеш, як і раніше: збір з новими новинами, `POST`, `PATCH`, `DELETE` окремої новини.
   Наявні тести кроку — зелені без змін.
7. Інвалідація лишається **після COMMIT**: не переносить `INCR` в ендпоінт.
8. `mypy --strict news_hub` — без помилок.

## Критерії приймання { #acceptance }

Поклади файл у `tests/test_cache_lab.py`. Тести дивляться на дві речі: заголовок `X-Cache` (що побачив клієнт) і
сам ключ `news:version` у Redis (чи було скидання).

```python title="tests/test_cache_lab.py"
"""Лаба 3: кеш пошуку й інвалідація лише тоді, коли дані справді змінились."""
from fastapi.testclient import TestClient

from news_hub.api import app

NEW = {"title": "Зеленський провів нараду з енергетиками", "url": "https://www.rbc.ua/ukr/news/lab-3.html"}


def version(client: TestClient) -> str | None:
    """Поточна версія кешу: кожен INCR — усі ключі кешу стають непотрібними."""
    value: str | None = client.portal.call(app.state.redis.get, "news:version")
    return value


def fill(client: TestClient) -> None:
    assert client.post("/api/scrape", json={"source": "snapshot"}).json()["news_saved"] == 168


# --- 1. Кеш пошуку -----------------------------------------------------------

def test_search_miss_then_hit(client: TestClient) -> None:
    fill(client)
    first = client.get("/api/news/search", params={"q": "зеленськ"})
    second = client.get("/api/news/search", params={"q": "зеленськ"})
    assert (first.headers.get("X-Cache"), second.headers.get("X-Cache")) == ("MISS", "HIT")
    assert first.json() == second.json() and len(first.json()) == 11


def test_search_key_ignores_case(client: TestClient) -> None:
    fill(client)
    client.get("/api/news/search", params={"q": "Зеленськ"})
    again = client.get("/api/news/search", params={"q": "ЗЕЛЕНСЬК"})
    assert again.headers["X-Cache"] == "HIT"                 # пошук без урахування регістру → один ключ


def test_search_other_limit_is_other_key(client: TestClient) -> None:
    fill(client)
    client.get("/api/news/search", params={"q": "зеленськ", "limit": 5})
    other = client.get("/api/news/search", params={"q": "зеленськ", "limit": 6})
    assert (other.headers["X-Cache"], len(other.json())) == ("MISS", 6)


def test_new_news_appears_in_cached_search(client: TestClient) -> None:
    fill(client)
    client.get("/api/news/search", params={"q": "зеленськ", "limit": 100})
    assert client.post("/api/news", json=NEW).status_code == 201
    after = client.get("/api/news/search", params={"q": "зеленськ", "limit": 100})
    assert (after.headers["X-Cache"], len(after.json())) == ("MISS", 12)


def test_search_validation_still_422(client: TestClient) -> None:
    assert client.get("/api/news/search", params={"q": "а"}).status_code == 422


# --- 2. Інвалідація лише після справжньої зміни -------------------------------

def test_scrape_without_new_news_keeps_cache(client: TestClient) -> None:
    fill(client)
    before = version(client)
    client.get("/api/news/stats")
    assert client.post("/api/scrape", json={"source": "snapshot"}).json()["news_saved"] == 0
    assert version(client) == before
    assert client.get("/api/news/stats").headers["X-Cache"] == "HIT"


def test_scrape_with_new_news_still_invalidates(client: TestClient) -> None:
    client.get("/api/news/stats")
    before = version(client)
    fill(client)
    assert version(client) != before
    stats = client.get("/api/news/stats")
    assert (stats.headers["X-Cache"], stats.json()["total"]) == ("MISS", 168)


def test_delete_all_on_empty_table_keeps_cache(client: TestClient) -> None:
    client.get("/api/news/stats")
    before = version(client)
    assert client.delete("/api/news").json() == {"deleted": 0}
    assert version(client) == before
    assert client.get("/api/news/stats").headers["X-Cache"] == "HIT"


def test_delete_all_with_news_invalidates(client: TestClient) -> None:
    fill(client)
    client.get("/api/news/stats")
    assert client.delete("/api/news").json() == {"deleted": 168}
    assert client.get("/api/news/stats").json()["total"] == 0


def test_background_job_without_new_news_keeps_cache(client: TestClient) -> None:
    fill(client)
    client.get("/api/news/stats")
    before = version(client)
    job_id = client.post("/api/scrape/jobs", json={"source": "snapshot"}).json()["job_id"]
    assert client.get(f"/api/scrape/jobs/{job_id}").json()["news_saved"] == 0
    assert version(client) == before
    assert client.get("/api/news/stats").headers["X-Cache"] == "HIT"
```

Три тести — `test_search_validation_still_422`, `test_scrape_with_new_news_still_invalidates`,
`test_delete_all_with_news_invalidates` — зелені вже до змін. Це навмисно: вони стережуть, щоб «менше скидань» не
перетворилось на «застарілий кеш».

**До змін:**

```text
$ pytest -q tests/test_cache_lab.py
FAILED tests/test_cache_lab.py::test_search_miss_then_hit - AssertionError: a...
FAILED tests/test_cache_lab.py::test_search_key_ignores_case - KeyError: 'X-C...
FAILED tests/test_cache_lab.py::test_search_other_limit_is_other_key - KeyErr...
FAILED tests/test_cache_lab.py::test_new_news_appears_in_cached_search - KeyE...
FAILED tests/test_cache_lab.py::test_scrape_without_new_news_keeps_cache - As...
FAILED tests/test_cache_lab.py::test_delete_all_on_empty_table_keeps_cache - ...
FAILED tests/test_cache_lab.py::test_background_job_without_new_news_keeps_cache
7 failed, 3 passed in 0.74s
```

**Після** — увесь набір кроку разом з новими тестами, і типи:

```text
$ pytest -q
51 passed in 3.08s
$ mypy --strict news_hub
Success: no issues found in 12 source files
```

Ті самі тести на справжніх PostgreSQL і Redis:

```text
$ TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5591/news_hub_test \
  TEST_REDIS_URL=redis://localhost:6391/15 pytest -q
51 passed in 7.02s
```

## Підказки { #hints }

??? tip "Пошук — той самий шаблон, що `list_news`"
    `cache.key(...)` → `cache.get(key)` → `HIT` або репозиторій → `NEWS_LIST.dump_json(...)` → `cache.set` →
    `cached_json(payload, "MISS")`. Ендпоінт тепер повертає `Response`, тому `response_model=list[NewsOut]`
    залиш у декораторі — інакше `/docs` втратить схему відповіді.

??? tip "Чому `q.lower()`, а не `q.casefold()`"
    Ключ має бути однаковим рівно тоді, коли однаковий результат. Пошук у базі — `lower(title) LIKE lower(…)`
    (у SQLite кроку 3 `lower()` замінено Python-версією `str.lower`). `casefold()` перетворює `"ß"` на `"ss"` —
    і два запити з різними результатами отримали б один ключ.

??? tip "Як ендпоінт передає щось у middleware"
    `request.state` — це словник з `scope` запиту, спільний для middleware й ендпоінта. В ендпоінт додай параметр
    типу `Request` (у `scrape` ім'я `request` уже зайняте тілом `ScrapeRequest` — назви інакше, наприклад
    `http: Request`). У middleware: `getattr(request.state, "news_changed", True)`.

??? tip "Фонова задача — не через middleware"
    `POST /api/scrape/jobs` відповідає `202` ще до збору, і шлях `/api/scrape/jobs` middleware не скидає взагалі.
    Кеш після фонового збору скидає сама `run_scrape_job` — після свого COMMIT. Саме там і умова `saved > 0`.

## Підхід до розв'язку { #solution }

??? success "Підхід до розв'язку"
    **Пошук з кешем** (`news_hub/api.py`):

    ```python
    @app.get("/api/news/search", response_model=list[NewsOut], tags=["news"], summary="Пошук у заголовках")
    async def search_news(
        repo: RepoDep,
        cache: CacheDep,
        q: str = Query(min_length=2, max_length=60, description="слово або частина слова"),
        limit: int = Query(20, ge=1, le=100),
    ) -> Response:
        """Оголошено ДО `/api/news/{news_id}`: інакше «search» потрапив би в news_id і отримав 422.

        Ключ — з q.lower(): пошук без урахування регістру, тож «Зеленськ» і «ЗЕЛЕНСЬК» — той самий результат.
        """
        key = await cache.key("search", {"q": q.lower(), "limit": limit})
        if (cached := await cache.get(key)) is not None:
            return cached_json(cached, "HIT")
        rows = await repo.search(q, limit)
        payload = NEWS_LIST.dump_json([NewsOut.model_validate(row) for row in rows]).decode()
        await cache.set(key, payload)
        return cached_json(payload, "MISS")
    ```

    **Ендпоінти кажуть, чи змінили дані** (`news_hub/api.py`, у `from fastapi import …` додай `Request`):

    ```python
    async def scrape(request: ScrapeRequest, repo: RepoDep, scrapers: ScrapersDep, http: Request) -> ScrapeReport:
        ...
        saved = await repo.add_many(valid)
        http.state.news_changed = saved > 0          # нічого нового — кеш не скидаємо (invalidate_cache)
        ...

    async def delete_all_news(repo: RepoDep, http: Request) -> dict[str, int]:
        deleted = await repo.clear()
        http.state.news_changed = deleted > 0
        return {"deleted": deleted}
    ```

    **Middleware читає прапорець** (`news_hub/middleware.py`):

    ```python
    response = await call_next(request)
    path = request.url.path
    changed = getattr(request.state, "news_changed", True)     # ендпоінт не сказав — вважаємо, що змінив
    if (request.method in WRITE_METHODS and response.status_code < 400 and changed
            and (path.startswith("/api/news") or path == "/api/scrape")):
        await NewsCache(get_redis(request)).invalidate()
    return response
    ```

    **Фоновий збір** (`news_hub/jobs.py`, `run_scrape_job`):

    ```python
    async with session_factory() as session:          # своя сесія: сесія запиту вже закрита
        saved = await NewsRepository(session).add_many(valid)
        await session.commit()
    if saved:
        await NewsCache(redis).invalidate()            # після COMMIT і лише якщо є нові новини
    ```

    Чому не «інвалідувати в ендпоінті, коли `saved > 0`»: COMMIT робить `get_db` уже **після** ендпоінта, і
    паралельний `GET` встиг би закешувати старі дані під новою версією — розбір у
    [кроці 4](../tutorials/04_middleware_redis/cache.md#commit). Прапорець переносить лише **рішення**, а сам `INCR`
    лишається після COMMIT.

## Що перевірити самому { #self-check }

- [ ] Прибери `and changed` з умови в `invalidate_cache`: мають впасти рівно
      `test_scrape_without_new_news_keeps_cache` і `test_delete_all_on_empty_table_keeps_cache`, а фоновий збір —
      ні. Чому?
- [ ] Зміни значення за замовчуванням у `getattr(..., True)` на `False`. Які наявні тести кроку впадуть, і що це
      каже про ендпоінти, які забудуть поставити прапорець?
- [ ] Запусти сервер з `REDIS_URL=redis://…`, зроби кілька пошуків і подивись `redis-cli --scan --pattern 'news:*:search:*'`
      і `TTL` одного ключа. Скільки ключів пошуку може бути в Redis одночасно?
- [ ] `PATCH /api/news/{id}` з тими самими значеннями, що вже є, теж скидає кеш. Варто це виправляти? Що коштує
      перевірка «чи змінилось» і що коштує зайве скидання?
- [ ] Ускладнення: **cache stampede**. Після `INCR` усі паралельні читачі одночасно отримують `MISS` і йдуть у базу.
      Як `SET key … NX EX 5` («хто перший, той рахує», решта коротко чекає або віддає застарілу версію) зменшив би
      навантаження? Як би ти це протестував?
- [ ] Можеш пояснити, чому прапорець ставить ендпоінт, а `INCR` робить middleware, і що зламається, якщо
      поміняти їх місцями.
