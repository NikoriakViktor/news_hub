# FastAPI над `NewsItem`

> Крок 2 · розділ 1 з 5. Код: [`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/02_fastapi_basics/news_hub/api.py).
> Теорія: [Маршрути, параметри і валідація](../../03_fastapi_core/routes_and_validation.md).

## Задача { #task }

Віддати перевірені новини по HTTP: `GET /api/news` зі списком, фільтрами за категорією, джерелом і мовою, пагінацією `skip`/`limit`. Неправильні параметри (`limit=0`, `lang=en`) не повинні дійти до нашого коду.

## Зміна: застосунок і перший ендпоінт { #change }

FastAPI будує API з **анотацій типів**. Параметр функції стає параметром запиту, його тип і `Query(...)` — правилами перевірки, а `response_model` — формою відповіді. Це той самий Pydantic, що в кроці 1, тільки тепер на вході й виході HTTP.

```python title="news_hub/api.py (фрагмент)"
app = FastAPI(
    title="news_hub API",
    version="0.37.0",
    lifespan=lifespan,                      # розділ 2
    openapi_tags=[...],                     # групи ендпоінтів у /docs
)


@app.get("/api/news", response_model=list[NewsItem], tags=["news"], summary="Список новин")
async def list_news(
    store: StoreDep,                        # розділ 2: сховище через Depends
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    category: str = Query("", description="Новини, Економіка, …"),
    source: str = Query("", description="rbc.ua, auto.rbc.ua, …"),
    lang: Literal["uk", "ru"] | None = Query(None),
) -> list[NewsItem]:
    """Новини з фільтрами й пагінацією: `?lang=uk&limit=5`."""
    return store.find(skip=skip, limit=limit, category=category, source=source, lang=lang or "")
```

Що тут робить FastAPI без жодного рядка нашого коду:

| Запис | Що відбувається з запитом `GET /api/news?limit=abc&lang=en` |
|---|---|
| `limit: int = Query(50, ge=1, le=1000)` | `"abc"` → не число → `422`; `0` → менше `ge=1` → `422`; немає → `50` |
| `lang: Literal["uk", "ru"] \| None` | `"en"` → не зі списку → `422` |
| `response_model=list[NewsItem]` | відповідь перетворюється на JSON за моделлю: `url` → рядок, `published_time` → `"14:19:00"` |
| `tags`, `summary`, docstring | потрапляють в OpenAPI → `/docs` |

Поруч — службові ендпоінти, без параметрів:

```python title="news_hub/api.py (фрагмент)"
@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/news/count", tags=["news"])
async def news_count(store: StoreDep) -> dict[str, int]:
    return {"count": store.count()}
```

Тут `response_model` немає: FastAPI бере форму відповіді з анотації результату `-> dict[str, int]`.

## Результат: запуск і перші запити { #result }

З папки `steps/02_fastapi_basics`:

```bash
pip install -r requirements.txt
uvicorn news_hub.api:app --reload      # INFO: Uvicorn running on http://127.0.0.1:8000
```

`news_hub.api:app` означає «модуль `news_hub/api.py`, змінна `app`». `--reload` перезапускає сервер, коли змінюється код.

У другому терміналі (або в Python-консолі) — запити клієнтом `httpx`:

```python
import httpx

api = httpx.Client(base_url="http://127.0.0.1:8000")
print(api.get("/health").json())
print(api.get("/api/news").json(), api.get("/api/news/count").json())
```

```text
{'status': 'ok'}
[] {'count': 0}
```

Сховище порожнє: новин ще ніхто не збирав. Зберемо зі знімка (168 новин з кроку 1). Сам ендпоінт збору розбирає [розділ 3](scrape_endpoint.md):

```python
report = api.post("/api/scrape", json={"source": "snapshot"}).json()
print({key: report[key] for key in ("news_found", "news_valid", "news_saved", "news_total")})

response = api.get("/api/news", params={"lang": "uk", "limit": 2})
print(response.status_code, response.headers["content-type"])
for news in response.json():
    print(news)
print(api.get("/api/news/stats").json())
```

```text
{'news_found': 168, 'news_valid': 168, 'news_saved': 168, 'news_total': 168}
200 application/json
{'title': 'Реформа ВСУ', 'url': 'https://www.rbc.ua/ukr/news/reforma-zsu-kih-zmin-armiyi-chekati-vzhe-1777644218.html', 'source': 'rbc.ua', 'lang': 'uk', 'category': 'Новини', 'published_time': None}
{'title': 'Долги теплокоммунэнерго перед "Нафтогазом" превысили 150 млрд грн, - Свириденко', 'url': 'https://www.rbc.ua/ukr/news/borgi-teplokomunenergo-pered-naftogazom-perevishchili-1778323211.html', 'source': 'rbc.ua', 'lang': 'uk', 'category': 'Новини', 'published_time': None}
{'total': 168, 'category': {'Новини': 168}, 'lang': {'ru': 138, 'uk': 30}, 'source': {'rbc.ua': 167, 'auto.rbc.ua': 1}}
```

Два спостереження:

- `published_time` у JSON — `null`: у цих двох новин у стрічці не було часу. Для інших — рядок `"HH:MM:SS"`: `response_model` перетворює `time` на JSON сам.
- Обидві новини лежать під `/ukr/`, тож `lang="uk"`, а заголовки — російською («Реформа ВСУ», «Долги …»). Мову ми **виводимо з URL**, а не з тексту, і сайт не завжди кладе текст туди, куди обіцяє адреса. Визначати мову за змістом агрегатор навчиться з LLM у [кроці 7](../07_llm_api/index.md).

## 422: помилка перевірки { #errors }

Неправильні параметри до нашої функції навіть не доходять. FastAPI відповідає `422 Unprocessable Content` з переліком помилок:

```python
for params in ({"limit": 0}, {"limit": "abc"}, {"lang": "en"}):
    response = api.get("/api/news", params=params)
    error = response.json()["detail"][0]
    print(response.status_code, params, "→", error["loc"], error["msg"])
```

```text
422 {'limit': 0} → ['query', 'limit'] Input should be greater than or equal to 1
422 {'limit': 'abc'} → ['query', 'limit'] Input should be a valid integer, unable to parse string as an integer
422 {'lang': 'en'} → ['query', 'lang'] Input should be 'uk' or 'ru'
```

Повна відповідь на `?limit=0`:

```json
{"detail": [{"type": "greater_than_equal", "loc": ["query", "limit"],
             "msg": "Input should be greater than or equal to 1", "input": "0", "ctx": {"ge": 1}}]}
```

| Поле | Що каже |
|---|---|
| `loc` | де помилка: `["query", "limit"]` — параметр рядка запиту `limit`; для тіла запиту буде `["body", …]` |
| `msg` | що не так, людською мовою |
| `type` | код помилки для програм: `greater_than_equal`, `int_parsing`, `literal_error`… |
| `input` | що прийшло (рядок `"0"`: у URL усе — рядки) |

Той самий формат отримає і Postman, і фронтенд, і бот: один раз навчився читати — читаєш скрізь.

## Звідки взялося ядро { #origin }

API не писали з нуля. Основа — FastAPI-прототип агрегатора `news_dashboard` з курсу: 618 рядків, 16 ендпоінтів, MongoDB, NLP, архівний парсер. Для першого кроку це забагато, тож узяли ядро, а решту перенесли в кроки, де для неї з'являється основа:

| Ендпоінти прототипу | Що з ними | Де повернуться |
|---|---|---|
| `/health`, `GET /api/news`, `/count`, `/stats`, `POST /api/scrape`, `DELETE /api/news` | **беремо** — ядро | цей крок |
| MongoDB у кожному ендпоінті | → `NewsStore` через `Depends` | [крок 3](../03_sqlalchemy_alembic/index.md) — SQLAlchemy |
| архівний збір і `/api/scrape/jobs` (`BackgroundTasks`) | фоновий збір | [крок 4](../04_middleware_redis/index.md) |
| `/keywords`, `/entities`, `/reanalyze` (spaCy, langdetect) | аналіз тексту | [крок 7](../07_llm_api/index.md) — LLM |
| `/trends`, `/timeline` (`$regex` з рядка користувача) | пошук | крок 3 (SQL); безпека — [крок 8](../08_security/index.md) |
| CORS `allow_origins=["*"]` + `allow_credentials=True` | прибрано: браузерного клієнта немає | — |

І що змінилося в тому, що взяли:

| Було в прототипі | Стало | Навіщо |
|---|---|---|
| друга модель новини — 13 полів окремо від парсера | `response_model=list[NewsItem]` з кроку 1 | одна модель на весь проєкт |
| `lang: str = Query(default="", description="uk \| ru \| unknown")` | `lang: Literal["uk", "ru"] \| None` | `?lang=en` — `422`, а не порожній список |
| `mode: str = Field(pattern="^(async\|sequential)$")` | `mode: Literal["async", "sequential"]` | те саме без regex; mypy знає значення |
| `from fastapi import HTTPException` усередині функцій | імпорти вгорі модуля | читабельність |
| 16 ендпоінтів | 6 + `openapi_tags` | ядро, згруповане в `/docs` |

## Правило { #rule }

!!! tip "Правило"
    Опиши параметр типом і обмеженням (`int`, `Query(ge=1)`, `Literal[...]`), а не перевіряй його `if`-ами всередині функції. Тоді перевірка, `422` з точним місцем помилки й опис у `/docs` з'являються разом і не розходяться.

**Далі:** [Сховище через `Depends` і `lifespan`](depends_and_lifespan.md) — звідки береться `store: StoreDep`.
