# Шпаргалка FastAPI

Усі фрагменти — з [`examples/reference/cheatsheet_check.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/reference/cheatsheet_check.py):
скрипт запускає кожен через `TestClient`, рядки «→» нижче — його вивід (FastAPI 0.162).

```bash
cd examples/reference
pip install -r requirements.txt
python cheatsheet_check.py
```

## Застосунок і запуск { #app }

| Що | Як | Докладно |
|---|---|---|
| створити застосунок | `app = FastAPI(title="…", lifespan=lifespan)` | [Що таке FastAPI](../03_fastapi_core/what_is_fastapi.md) |
| запустити для розробки | `uvicorn news_hub.api:app --reload` (з папки, де видно пакет) | [крок 2](../tutorials/02_fastapi_basics/fastapi_app.md) |
| те саме через CLI FastAPI | `fastapi dev news_hub/api.py` — потрібен `pip install "fastapi[standard]"` | [Що таке FastAPI](../03_fastapi_core/what_is_fastapi.md#mistakes) |
| запустити в контейнері | `uvicorn news_hub.api:app --host 0.0.0.0 --port 8000` | [крок 10](../tutorials/10_docker/index.md) |
| документація | `/docs` (Swagger UI), `/redoc`, `/openapi.json` | [OpenAPI](../03_fastapi_core/openapi.md) |

## Маршрути { #routes }

| Що | Як | Докладно |
|---|---|---|
| метод і шлях | `@app.get` / `post` / `put` / `patch` / `delete("/api/news/{news_id}")` | [Маршрути](../03_fastapi_core/routes_and_validation.md) |
| код успіху | `status_code=status.HTTP_201_CREATED` | [Коди відповідей](../01_http_and_rest/status_codes.md) |
| модель відповіді | `response_model=NewsOut` або анотація `-> NewsOut` | [Маршрути](../03_fastapi_core/routes_and_validation.md) |
| опис для `/docs` | `tags=["news"]`, `summary="…"`, `responses={404: {"description": "…"}}` | [OpenAPI](../03_fastapi_core/openapi.md) |
| залежність без значення | `dependencies=[AdminDep]` | [Залежності](../03_fastapi_core/dependencies.md#levels) |
| порядок | конкретні шляхи (`/api/news/search`) — **до** `/api/news/{news_id}` | [Порядок маршрутів](../03_fastapi_core/routes_and_validation.md#route-order) |
| коса риска | `/api/news/` для маршруту `/api/news` → `307` на адресу без `/` | [HTTP-запит і відповідь](../01_http_and_rest/http_anatomy.md) |

## Параметри { #params }

Звідки береться значення, FastAPI вирішує за типом і маркером: простий тип у шаблоні шляху — path, інший простий
тип — query, модель Pydantic — тіло JSON.

| Звідки | Оголошення | Помилка в `loc` |
|---|---|---|
| шлях | `item_id: Annotated[int, Path(ge=1)]` | `["path", "item_id"]` |
| рядок запиту | <code>q: Annotated[str &#124; None, Query(max_length=50)] = None</code> | `["query", "q"]` |
| список у рядку запиту | `tags: Annotated[list[str], Query()] = []` → `?tags=a&tags=b` | `["query", "tags", 0]` |
| усі параметри запиту однією моделлю | `filters: Annotated[Filters, Query()]` | `["query", "sort"]` |
| заголовок | <code>x_token: Annotated[str &#124; None, Header()] = None</code> → заголовок `X-Token` | `["header", "x-token"]` |
| cookie | <code>session: Annotated[str &#124; None, Cookie()] = None</code> | `["cookie", "session"]` |
| тіло JSON | `body: NewsIn` | `["body", "title"]` |
| одне поле тіла | `score: Annotated[int, Body(embed=True, ge=1, le=5)]` → `{"score": 5}` | `["body", "score"]` |
| форма | `username: Annotated[str, Form()]` — потрібен `python-multipart` | `["body", "username"]` |
| файл | `file: Annotated[UploadFile, File()]` — теж `python-multipart` | `["body", "file"]` |
| увесь запит | `request: Request` (`request.app.state`, `request.headers`, `await request.body()`) | — |

```python
class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")      # невідомий параметр рядка запиту → 422
    lang: Literal["uk", "ru"] = "uk"
    limit: int = Field(20, ge=1, le=100)


@app.get("/items/{item_id}")
def read_item(
    item_id: Annotated[int, Path(ge=1)],
    q: Annotated[str | None, Query(max_length=50)] = None,
    tags: Annotated[list[str], Query()] = [],
    x_token: Annotated[str | None, Header()] = None,          # заголовок X-Token
    session: Annotated[str | None, Cookie()] = None,
) -> dict[str, object]:
    return {"item_id": item_id, "q": q, "tags": tags, "x_token": x_token, "session": session}


@app.get("/news")
def list_news(filters: Annotated[Filters, Query()]) -> Filters:
    return filters
```

```text
path + query + header + cookie     → 200 {'item_id': 7, 'q': 'ai', 'tags': ['a', 'b'], 'x_token': 't', 'session': 's1'}
path ge=1                          → 422 {'detail': 'неправильні дані', 'fields': ['path.item_id']}
query-модель                       → 200 {'lang': 'ru', 'limit': 5}
query-модель, extra=forbid         → 422 {'detail': 'неправильні дані', 'fields': ['query.sort']}
тіло: модель                       → 201 {'title': 'Заголовок новини', 'category': 'Новини', 'id': 1}
тіло: коротке поле                 → 422 {'detail': 'неправильні дані', 'fields': ['body.title']}
Body(embed=True)                   → 200 {'score': 5}
Form                               → 200 {'username': 'admin'}
File                               → 200 {'filename': 'a.txt', 'size': 5}
```

Формат `422` тут змінено власним обробником ([нижче](#exception-handlers)); стандартний — `{"detail": [{"type",
"loc", "msg", "input"}]}`, див. [`ValidationError`](../02_typing_and_pydantic/validation_error.md).

- `x_token` → `X-Token`: підкреслення в імені параметра стає дефісом. Заголовок `X_Token` з підкресленням nginx
  за замовчуванням відкидає ([HTTP-запит і відповідь](../01_http_and_rest/http_anatomy.md#mistakes)).
- `str | None` без `= None` — **обов'язковий** параметр, який може бути `null`
  ([анотації типів](../02_typing_and_pydantic/type_hints.md)).

## Відповіді й коди { #responses }

| Що | Як |
|---|---|
| JSON | повернути `dict`, список або модель; `response_model` відфільтрує зайві поля |
| `201`, `202`, `204` | `status_code=` у декораторі; для `204` — `return Response(status_code=204)` без тіла |
| помилка | `raise HTTPException(status.HTTP_404_NOT_FOUND, detail="…", headers={…})` |
| свій заголовок | параметр `response: Response` → `response.headers["X-Cache"] = "MISS"` |
| готовий JSON-рядок | `Response(content=payload, media_type="application/json")` — так кеш News Hub віддає `HIT` |
| свій код і тіло | `JSONResponse({"status": "unavailable"}, status_code=503)` — `/health/ready` |
| `422` у новому коді | `status.HTTP_422_UNPROCESSABLE_CONTENT` або просто `422` (`…_ENTITY` застаріла) |

```python
@app.post("/news", status_code=status.HTTP_201_CREATED, response_model=NewsOut)
def create_news(body: NewsIn) -> dict[str, object]:
    return {"id": 1, **body.model_dump(), "secret": "не потрапить у відповідь"}


@app.delete("/news/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_news(news_id: int) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/headers")
def with_headers(response: Response) -> dict[str, bool]:
    response.headers["X-Cache"] = "MISS"
    return {"ok": True}
```

```text
HTTPException 404                  → 404 {'error': 'новини 99 немає'}
204 без тіла                       → 204 b''
заголовок через Response           → 200 X-Cache=MISS
```

Усі коди, які повертає News Hub, — у [Кодах відповідей](http_status_codes.md).

## `Depends` { #depends }

| Що | Як | Докладно |
|---|---|---|
| залежність | функція з параметрами, як у маршруту: `Annotated[dict, Depends(pagination)]` | [Залежності](../03_fastapi_core/dependencies.md) |
| з прибиранням | `yield` у функції; код після `yield` — після ендпоінта | [`yield`](../03_fastapi_core/dependencies.md#yield-timing) |
| прибирання до відповіді | `Depends(get_db, scope="function")` (FastAPI ≥ 0.121); за замовчуванням `"request"` — після відповіді | [сесія на запит, крок 3](../tutorials/03_sqlalchemy_alembic/session_per_request.md#scope) |
| псевдонім | `SessionDep = Annotated[AsyncSession, Depends(get_db, scope="function")]` | `steps/12_ci_cd/news_hub/api.py` |
| на маршрут, роутер, застосунок | `dependencies=[…]` у декораторі, `APIRouter(…)`, `FastAPI(…)` | [Де підключати](../03_fastapi_core/dependencies.md#levels) |
| підміна в тестах | `app.dependency_overrides[get_llm_client] = lambda: FakeLLM()`; потім `.clear()` | [крок 7](../tutorials/07_llm_api/endpoints_and_tests.md) |
| кеш на запит | та сама залежність двічі в одному запиті — один виклик (`use_cache=False` — щоразу заново) | нижче |

```python
def pagination(skip: int = 0, limit: int = Query(20, le=100)) -> dict[str, int]:
    CALLS.append("pagination")
    return {"skip": skip, "limit": limit}


def get_db() -> Iterator[str]:
    CALLS.append("db: open")
    try:
        yield "session"
    finally:
        CALLS.append("db: close")


Page = Annotated[dict[str, int], Depends(pagination)]
Db = Annotated[str, Depends(get_db, scope="function")]       # прибирання ДО відповіді


@app.get("/deps")
def deps(page: Page, again: Page, db: Db) -> dict[str, object]:
    return {"page": page, "same_object": page is again, "db": db}
```

```text
дві однакові залежності            → 200 {'page': {'skip': 0, 'limit': 20}, 'same_object': True, 'db': 'session'}
виклики: ['pagination', 'db: open', 'db: close']
```

`Depends(get_db)` без дужок після `get_db`: `Depends(get_db())` викликає функцію один раз при імпорті.

## `lifespan` { #lifespan }

Ресурси на весь час роботи процесу: пул з'єднань, клієнт Redis, HTTP-клієнт LLM, бот. До `yield` — старт,
після — зупинка. `@app.on_event("startup")` застарів (`DeprecationWarning`).

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.store = {"1": "перша новина"}      # ресурс на весь час роботи сервера
    EVENTS.append("startup")
    yield
    EVENTS.append("shutdown")                    # закрити пул, клієнта, з'єднання


app = FastAPI(title="cheatsheet", lifespan=lifespan)
```

У маршруті ресурс береться з `request.app.state.store`. Докладно — [`lifespan`](../03_fastapi_core/dependencies.md#lifespan),
у News Hub — [крок 2](../tutorials/02_fastapi_basics/depends_and_lifespan.md).

## Middleware { #middleware }

| Що | Як | Докладно |
|---|---|---|
| функція навколо кожного запиту | `@app.middleware("http")` або `app.middleware("http")(fn)`; `response = await call_next(request)` | [крок 4](../tutorials/04_middleware_redis/middleware.md) |
| клас Starlette | `app.add_middleware(CORSMiddleware, allow_origins=[…], …)` | [CORS](../06_middleware_cache_jobs/cors.md) |
| порядок | зареєстрований **останнім** — зовнішній: першим бачить запит, останнім — відповідь | нижче |
| відповідь без `call_next` | `return JSONResponse(status_code=429, …)` — ендпоінт не викликається | [rate limit](../tutorials/04_middleware_redis/rate_limit.md) |

```python
@app.middleware("http")
async def inner(request: Request, call_next):
    ORDER.append("inner ←")
    response = await call_next(request)
    ORDER.append("inner →")
    return response


@app.middleware("http")
async def outer(request: Request, call_next):
    ORDER.append("outer ←")                     # зареєстрований останнім — зовнішній
    response = await call_next(request)
    response.headers["X-Process"] = "ok"
    ORDER.append("outer →")
    return response
```

```text
порядок middleware: ['outer ←', 'inner ←', 'inner →', 'outer →'] | X-Process: ok
```

## Обробники винятків { #exception-handlers }

| Що перехопити | Клас | Коли спрацює |
|---|---|---|
| свій виняток домену | `@app.exception_handler(LLMError)` | `raise LLMError` у маршруті чи залежності |
| помилки перевірки запиту | `fastapi.exceptions.RequestValidationError` | `422` від параметрів і тіла |
| усі HTTP-помилки | `starlette.exceptions.HTTPException` | і `raise HTTPException`, і `404`/`405` маршрутизатора |
| лише `raise HTTPException` | `fastapi.HTTPException` | `404`/`405` маршрутизатора — **не** перехоплює |

```python
@app.exception_handler(LLMError)
async def llm_error(request: Request, error: LLMError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"провайдер недоступний: {error}"})


@app.exception_handler(StarletteHTTPException)      # і 404/405 маршрутизатора, не лише raise HTTPException
async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"error": error.detail},
                        headers=error.headers)
```

```text
невідомий шлях (handler)           → 404 {'error': 'Not Found'}
метод не той (handler)             → 405 {'error': 'Method Not Allowed'}
свій виняток → 502                 → 502 {'detail': 'провайдер недоступний: timeout'}
```

`headers=error.headers` — щоб не загубити `WWW-Authenticate` і `Retry-After`. Докладно —
[Формат помилок](../01_http_and_rest/errors.md); у News Hub `LLMError` → `502`/`503` —
[крок 7](../tutorials/07_llm_api/endpoints_and_tests.md).

## `APIRouter` { #router }

```python
admin = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_token)])


@admin.get("/stats")
def admin_stats() -> dict[str, int]:
    return {"total": 1}


app.include_router(admin)
```

```text
router без токена                  → 422 {'detail': 'неправильні дані', 'fields': ['header.x-token']}
router з токеном                   → 200 {'total': 1}
dependency_overrides               → 200 {'total': 1}
APIRouter(prefix='/v1/') → AssertionError: A path prefix must not end with '/', as the routes will start with '/'
```

Без заголовка — `422`, а не `401`: обов'язковий `Header()` перевіряється раніше за код залежності. News Hub тому
бере токен через `HTTPBearer(auto_error=False)` і сам відповідає `401` з `WWW-Authenticate`
([крок 8](../tutorials/08_security/admin_jwt.md)). Версії API роутерами — [Версіонування](../01_http_and_rest/versioning.md).

## `BackgroundTasks` { #background }

```python
@app.post("/notify", status_code=status.HTTP_202_ACCEPTED)
def start_notify(background: BackgroundTasks) -> dict[str, int]:
    background.add_task(notify, "нова новина")      # після відправлення відповіді
    return {"queued": len(SENT)}
```

```text
BackgroundTasks                    → 202 {'queued': 0}
після відповіді SENT = ['нова новина']
```

Задача виконується в тому самому процесі після відповіді: перезапуск сервера її губить. `TestClient` чекає на
фонові задачі, справжній сервер — ні. У News Hub — `202` + `job_id` і статус у Redis
([крок 4](../tutorials/04_middleware_redis/background_jobs.md)).

## Тестування { #testing }

| Що | Як | Докладно |
|---|---|---|
| синхронний клієнт | `with TestClient(app) as client:` — `with` запускає `lifespan` | [крок 2](../tutorials/02_fastapi_basics/checkpoint.md#mistakes) |
| асинхронний клієнт | `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")` | [крок 5](../tutorials/05_api_testing/async_client.md) |
| `lifespan` для `AsyncClient` | `async with app.router.lifespan_context(app):` | нижче |
| підміна залежності | `app.dependency_overrides[dep] = fake` → `.clear()` у фікстурі | [Залежності](../03_fastapi_core/dependencies.md#mistakes) |
| маркери | `pytest -m unit`, `-m integration`, `-m llm`, `-m docker` | [Команди](commands.md#tests) |

```python
async def async_check() -> None:
    async with app.router.lifespan_context(app):         # ASGITransport сам lifespan не запускає
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            show("AsyncClient", await client.get("/news/1"))
```

```text
events після старту: ['startup']
...
events після with: ['startup', 'shutdown']
AsyncClient                        → 200 {'title': 'перша новина'}
```

## `async def` чи `def` { #async-def }

| Ендпоінт | Де виконується | Коли |
|---|---|---|
| `async def` + `await` | цикл подій | async-бібліотеки: `httpx`, `aiohttp`, `asyncpg`, `redis.asyncio` |
| `def` | пул потоків (40 за замовчуванням) | блокуючі бібліотеки |
| `async def` + блокуючий виклик | цикл подій, і він стоїть | ніколи |

Виміри — [Архітектура](architecture.md#endpoint-types) і [крок 2](../tutorials/02_fastapi_basics/async_measurements.md).

## Що далі { #next }

- [Шпаргалка Pydantic](pydantic_cheatsheet.md) — моделі, що стоять за параметрами й відповідями.
- [Частина III. Ядро FastAPI](../03_fastapi_core/README.md) — те саме з поясненнями.
