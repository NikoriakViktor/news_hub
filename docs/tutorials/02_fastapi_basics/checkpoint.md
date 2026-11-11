# Контрольна точка: крок 2

## Перевір, що крок робочий { #check }

З папки `steps/02_fastapi_basics`:

```text
$ pytest -q -p no:cacheprovider
.......................                                                  [100%]
23 passed in 0.76s
$ mypy --strict news_hub
Success: no issues found in 7 source files
```

Порівняно з кроком 1 додалось 11 тестів API: порожнє сховище, збір зі знімка й фільтри, повторний збір, відхилені новини від скрапера-заглушки, чотири випадки `422`, очищення, перелік шляхів в OpenAPI.

## Чекліст { #checklist }

- [ ] `uvicorn news_hub.api:app --reload` запускається, `/health` відповідає `{"status": "ok"}`.
- [ ] `POST /api/scrape` з `{"source": "snapshot"}` → `news_saved: 168`; удруге → `news_saved: 0`.
- [ ] `GET /api/news?lang=uk&limit=2` повертає дві новини; `?limit=0` → `422` з `loc: ["query", "limit"]`.
- [ ] У `/docs` три групи: `news`, `scrape`, `system`.
- [ ] Колекція Postman проходить: 7 запитів, 12 перевірок.
- [ ] Можеш пояснити, чому `/sync-broken` на 10 запитах триває ~20 с, а `/sync-safe` — ~2 с.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `Error loading ASGI app. Could not import module "news_hub.api"` | uvicorn запущено не з папки кроку | `cd steps/02_fastapi_basics`, потім `uvicorn news_hub.api:app` |
| `AttributeError: 'State' object has no attribute 'store'` у тесті | `TestClient(app)` без `with` — `lifespan` не запустився | `with TestClient(app) as client:` |
| `422` на запит, який «точно правильний» | параметр передано не туди: модель — у тілі JSON, простий тип — у рядку запиту | дивись `loc`: `["query", …]` чи `["body", …]` |
| `POST /api/scrape` повертає сторінки з `error: ClientResponseError: 403` | сайт не пускає запити з твоєї мережі | працюй зі знімком: `{"source": "snapshot"}` |
| `[Errno 98] address already in use` (Windows: `[WinError 10048]`) | порт 8000 зайнятий іншим процесом | `uvicorn ... --port 8010` |

## Практика { #practice }

### Розібраний приклад: `GET /api/news/sources` { #worked-example }

Задача: список джерел з кількістю новин — `{"rbc.ua": 167, "auto.rbc.ua": 1}`.

1. **Шлях і метод.** Читаємо, отже `GET`; ресурс — джерела новин → `/api/news/sources`.
2. **Звідки дані.** `store.stats()["source"]` уже рахує джерела, нової логіки не треба.
3. **Що повертаємо.** `dict[str, int]`: анотація результату одразу стає схемою в `/docs`.

```python
from fastapi.testclient import TestClient
from news_hub.api import StoreDep, app


@app.get("/api/news/sources", tags=["news"])
async def news_sources(store: StoreDep) -> dict[str, int]:
    """Джерела новин і скільки новин з кожного."""
    return store.stats()["source"]


with TestClient(app) as client:
    client.post("/api/scrape", json={"source": "snapshot"})
    print(client.get("/api/news/sources").json())
    print("/api/news/sources" in client.get("/openapi.json").json()["paths"])
```

```text
{'rbc.ua': 167, 'auto.rbc.ua': 1}
True
```

Порядок маршрутів має значення. Якби в застосунку був маршрут `/api/news/{news_id}`, оголошений **раніше**, запит `/api/news/sources` потрапив би в нього з `news_id="sources"`. Конкретні шляхи оголошуй перед шляхами з параметрами — [докладніше](../../03_fastapi_core/routes_and_validation.md#route-order).

### Зміни приклад { #modify }

1. Додай до `/api/news/sources` параметр `min_count: int = Query(1, ge=1)` — повертати лише джерела, де новин не менше `min_count`. Перевір `422` для `min_count=0`.
2. Додай у колекцію Postman запит «8. джерела» з перевіркою, що сума значень дорівнює `total` зі збору.

### Спробуй самостійно: пошук за словом { #search }

Ендпоінт `GET /api/news/search?q=…`:

- `q` — обов'язковий, 2–60 символів (`Query(min_length=2, max_length=60)`);
- шукає `q` у заголовку без урахування регістру (`q.lower() in item.title.lower()`), повертає `list[NewsItem]`;
- пошук — метод `NewsStore.search(q, limit)`, а не код в ендпоінті.

**Критерії перевірки:** `?q=Зеленськ` на знімку повертає лише новини з цим словом у заголовку (у знімку їх 11); `?q=а` → `422`; тест у `tests/test_api.py`; `mypy --strict` чистий.

У прототипі `/api/news/trends` робив пошук через `$regex` з рядка користувача. Чому так не варто — [крок 8](../08_security/index.md).

### Знайди помилку { #find-bug }

Студент додав ендпоінт «зібрати одну сторінку» через `requests`:

```python title="news_hub/api.py"
import requests

@app.post("/api/scrape/page")
async def scrape_page(url: str, store: StoreDep) -> dict[str, int]:
    html = requests.get(url, timeout=15).text
    valid, _ = validate_news(parse_rbc_news(html))
    return {"saved": store.add_many(valid)}
```

Локально з одним користувачем усе працює. Що станеться, коли rbc.ua відповідатиме 10 секунд, а до агрегатора прийде ще кілька запитів? Знайди дві проблеми.

??? success "Відповідь"

    1. **`requests.get` у `async def` блокує цикл подій.** Поки сторінка вантажиться (до 15 с), сервер не відповідає нікому, навіть `/health`. Це `/sync-broken` з [вимірів](async_measurements.md#results): 10 таких запитів — 10 × час сторінки. Виправлення: асинхронний клієнт з `await` (`aiohttp`, як у `scraper.py`, або `httpx.AsyncClient`) або `def` замість `async def`, щоб FastAPI виконав функцію в пулі потоків.
    2. **`url: str` без перевірки — SSRF.** Будь-хто може попросити сервер завантажити `http://localhost:…` чи внутрішню адресу. Виправлення: `HttpUrl` і перевірка домену, як у `ScrapeRequest.only_rbc`.

    Бонус: `url: str` без моделі — це параметр **рядка запиту** (`POST /api/scrape/page?url=…`), а не тіла. Для `POST` з даними краще модель у тілі.

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| `FastAPI()` + `@app.get/post/delete` | маршрут = метод + шлях → функція |
| Параметри | простий тип — з рядка запиту; Pydantic-модель — з тіла; `Depends` — із залежності |
| `Query(..., ge=, le=)`, `Literal` | правила перевірки параметрів; порушення → `422` |
| `422` | `detail[i].loc` — де помилка, `msg` — що не так |
| `response_model` | форма відповіді й JSON з моделі |
| `Depends`, `Annotated` | ендпоінт просить ресурс, FastAPI дає; у тестах — `dependency_overrides` |
| `lifespan` | код при старті й зупинці сервера (замість `on_event`) |
| `/docs`, `/redoc`, `/openapi.json` | опис API, який FastAPI будує сам |
| Postman / newman | збережені запити з перевірками; newman — те саме з консолі й CI |
| `async def` vs `def` | `async def` — у циклі подій, лише з `await`; блокуючий код — у `def` (пул потоків) або через async-бібліотеку |
| Вимір | перевір клієнт і тайм-аути, перш ніж робити висновки про сервер |

## Самоперевірка { #self-check }

1. Звідки FastAPI бере значення параметра `limit: int = Query(50)`, а звідки — `request: ScrapeRequest`?
2. Що поверне `GET /api/news?limit=0` і де у відповіді шукати причину?
3. Навіщо сховище в `Depends`, якщо можна створити глобальну змінну `store = NewsStore()`?
4. Що робить код до і після `yield` у `lifespan`?
5. Чим відрізняються `/docs` і колекція Postman? Коли що використовувати?
6. `async def` + `time.sleep(2)`, 20 одночасних запитів — скільки чекатиме останній і чому? А з `def`?
7. Чому `POST /api/scrape` приймає сторінки лише з rbc.ua? Що в цій перевірці ще не так?

??? success "Відповіді"

    1. `limit` — з рядка запиту (`?limit=5`), бо це простий тип; `ScrapeRequest` — Pydantic-модель, тому з JSON-тіла.
    2. `422`, `detail[0].loc == ["query", "limit"]`, `msg` — «Input should be greater than or equal to 1».
    3. Залежність можна підмінити в тестах (`dependency_overrides`) і замінити реалізацію (SQLAlchemy в кроці 3), не змінюючи ендпоінтів. Глобальна змінна жорстко зв'язує код з однією реалізацією і живе між тестами.
    4. До `yield` — один раз при старті (створити сховище, пул з'єднань), після — при зупинці (закрити, прибрати).
    5. `/docs` — спробувати запит тут і зараз, прочитати контракт. Postman — зберегти набір запитів із перевірками, поділитися з командою, проганяти в CI через newman.
    6. ~40 с: `time.sleep` займає цикл подій, запити виконуються по черзі (виміряно: 40.03 с). З `def` — ~2 с: FastAPI виконує функції в пулі потоків (виміряно: 2.03 с).
    7. Інакше будь-хто змусить сервер завантажити довільну адресу, зокрема внутрішню (SSRF). А `endswith("rbc.ua")` пропускає і `fakerbc.ua` — це виправить крок 5.

## Що далі { #next }

[Крок 3. База даних: SQLAlchemy і Alembic](../03_sqlalchemy_alembic/index.md) — `NewsStore` → SQLAlchemy: новини переживають перезапуск сервера, унікальний `url` стає обмеженням бази, `GET /api/news` — SQL-запитом з фільтрами.
