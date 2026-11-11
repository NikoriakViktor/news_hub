# Повний CRUD

> Крок 3 · розділ 4 з 5. Код: [`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/news_hub/api.py), [`tests/test_crud.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/tests/test_crud.py), [`postman/news_hub.postman_collection.json`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/postman/news_hub.postman_collection.json).
> Теорія: [Коди статусу](../../01_http_and_rest/status_codes.md), [HTTP-методи](../../01_http_and_rest/http_methods.md).

## Задача { #task }

У кожної новини тепер є `id`. API має вміти працювати з **однією** новиною: додати вручну, прочитати, змінити заголовок чи категорію, видалити. І відповідати правильними кодами, щоб клієнт без читання тексту помилки знав, що сталося.

| Дія | Метод і шлях | Успіх | Помилки |
|---|---|---|---|
| створити | `POST /api/news` | `201` + новина з `id` | `422` — не пройшла `NewsItem`; `409` — такий `url` уже є |
| прочитати | `GET /api/news/{news_id}` | `200` | `404`; `422` — `news_id` не число |
| змінити | `PATCH /api/news/{news_id}` | `200` | `404`, `422` |
| видалити | `DELETE /api/news/{news_id}` | `204`, без тіла | `404` |
| список, пошук | `GET /api/news`, `GET /api/news/search?q=` | `200` | `422` |

## Зміна 1: «знайди або `404`» — одна залежність { #row-dep }

Три ендпоінти з `{news_id}` починаються однаково: знайти новину, а якщо її немає — `404`. Цю спільну частину винесено в залежність:

```python title="news_hub/api.py (фрагмент)"
async def get_news_or_404(news_id: int, repo: RepoDep) -> NewsRow:
    row = await repo.get(news_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"новини {news_id} немає")
    return row


RowDep = Annotated[NewsRow, Depends(get_news_or_404)]


@app.get("/api/news/{news_id}", response_model=NewsOut, tags=["news"],
         responses={404: {"description": "такої новини немає"}})
async def get_news(row: RowDep) -> NewsRow:
    return row
```

- `news_id: int` у залежності — це параметр **шляху**: FastAPI бере його з `/api/news/{news_id}`. `/api/news/abc` → `422` з `loc: ["path", "news_id"]`, до бази запит не доходить.
- `responses={404: ...}` — лише опис для `/docs`; сам `404` дає `HTTPException`.
- Ендпоінт `get_news` — один рядок: усю роботу зробила залежність.

## Зміна 2: `POST /api/news` — `201`, `422`, `409` { #create }

```python title="news_hub/api.py (фрагмент)"
class NewsCreate(BaseModel):
    """Тіло POST /api/news — як сирий рядок парсера; перевіряє NewsItem."""
    title: str
    url: str
    published_time: str = ""


@app.post("/api/news", response_model=NewsOut, status_code=status.HTTP_201_CREATED, tags=["news"],
          responses={409: {"description": "новина з таким url уже є"}})
async def create_news(body: NewsCreate, repo: RepoDep) -> NewsRow:
    """Додати новину вручну. Перевірка — та сама модель NewsItem, що й для парсера."""
    try:
        item = NewsItem.from_raw({"title": body.title, "url": body.url, "category": "",
                                  "description": "", "datetime": body.published_time})
    except ValidationError as error:
        raise HTTPException(422,
                            detail=error.errors(include_url=False, include_context=False)) from error
    try:
        return await repo.create(item)
    except IntegrityError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"новина з url {item.url} уже є") from error
```

| Крок | Що відбувається | Код |
|---|---|---|
| `NewsCreate` | тіло — три рядки, як сирий рядок парсера | `422`, якщо тіло не JSON-об'єкт з `title` і `url` |
| `NewsItem.from_raw` | **та сама перевірка, що для парсера**: довжина заголовка, домен rbc.ua; мова, джерело й категорія виводяться з URL | `422` з помилками `NewsItem` |
| `repo.create` → `flush` | `INSERT` у межах транзакції | `201` |
| `IntegrityError` | база відхилила дублікат `url` | `409` |

`status_code=201` — успішне створення ресурсу, а не просто `200`. `409 Conflict` — запит правильний, але суперечить стану бази.

Перевірка `NewsItem` іде вручну, тож `422` тут має трохи іншу форму, ніж автоматичний: у `loc` немає `"body"`.

```text
422 {'detail': [{'type': 'string_too_short', 'loc': ['title'], 'msg': 'String should have at least 10 characters', 'input': 'Коротко'}, {'type': 'value_error', 'loc': ['url'], 'msg': 'Value error, очікуємо новину з rbc.ua', 'input': 'https://example.com/ukr/news/x.html'}]}
```

## Зміна 3: `PATCH` — лише передані поля { #patch }

```python title="news_hub/api.py (фрагмент)"
class NewsPatch(BaseModel):
    """PATCH: лише ті поля, які передали."""
    title: str | None = Field(None, min_length=10, max_length=300)
    category: str | None = Field(None, min_length=2, max_length=100)

    @field_validator("title", "category")
    @classmethod
    def not_null(cls, value: str | None) -> str:
        """Явний null — не «не змінювати», а спроба стерти обов'язкове поле: 422, а не 500 з NewsOut.
        Значення за замовчуванням валідатор не бачить, тож пропущене поле лишається непереданим."""
        if value is None:
            raise ValueError("поле не може бути null; не хочеш міняти — не передавай його")
        return value


@app.patch("/api/news/{news_id}", response_model=NewsOut, tags=["news"],
           responses={404: {"description": "такої новини немає"}})
async def update_news(body: NewsPatch, row: RowDep) -> NewsRow:
    """Змінити заголовок і/або категорію; поля, яких немає в тілі, не чіпаємо."""
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    return row
```

`exclude_unset=True` — серце `PATCH`. Що потрапляє в цикл для різних тіл:

```python
from pydantic import ValidationError
from news_hub.api import NewsPatch

for raw in ({"category": "Економіка"}, {"title": None}, {}):
    try:
        body = NewsPatch.model_validate(raw)
        print(raw, "→", body.model_dump(exclude_unset=True), "| без exclude_unset:", body.model_dump())
    except ValidationError as error:
        print(raw, "→ 422:", error.errors()[0]["msg"])
```

```text
{'category': 'Економіка'} → {'category': 'Економіка'} | без exclude_unset: {'title': None, 'category': 'Економіка'}
{'title': None} → 422: Value error, поле не може бути null; не хочеш міняти — не передавай його
{} → {} | без exclude_unset: {'title': None, 'category': None}
```

Без `exclude_unset` `PATCH {"category": …}` записав би в заголовок `None`. А `UPDATE` ендпоінт не пише: після `setattr` сесія знає, що рядок змінено, і `commit()` у `get_db` відправить `UPDATE` ([розділ 3](session_per_request.md#get-db)).

!!! warning "Навіщо `not_null`: без нього `PATCH {"title": null}` → `500`, а не `422`"
    **Явний** `null` вважається «переданим» полем, і `exclude_unset` його лишає. `Field(None, min_length=10)` не перевіряє `None` — тип `str | None` його дозволяє. Без валідатора далі було б `setattr(row, "title", None)`, а відповідь `NewsOut` вимагає `title: str`:

    ```text
    PATCH null 500 'Internal Server Error'
    ```

    ```text
    fastapi.exceptions.ResponseValidationError: 1 validation error:
      {'type': 'string_type', 'loc': ('response', 'title'), 'msg': 'Input should be a valid string', 'input': None}
    ```

    Те саме з `{"category": null}`. Дані не псуються: виняток виникає до COMMIT, `get_db` робить ROLLBACK, і наступний `GET` показує старий заголовок (перевірено на PostgreSQL і SQLite). Але клієнт отримує `500` замість `422` з поясненням. Так поводилася перша версія кроку, без `not_null`; повний розбір — вправа в [контрольній точці](checkpoint.md#find-bug-patch). Валідатор не чіпає пропущені поля: значення за замовчуванням Pydantic не перевіряє, тому `{}` і `{"category": …}` працюють, як раніше.

## Зміна 4: `DELETE` — `204` без тіла { #delete }

```python title="news_hub/api.py (фрагмент)"
@app.delete("/api/news/{news_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["news"],
            responses={404: {"description": "такої новини немає"}})
async def delete_news(row: RowDep, repo: RepoDep) -> Response:
    await repo.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

`204 No Content` означає «зроблено, і тіла немає». Тому ендпоінт повертає порожню `Response`, а не словник. `RowDep` і `RepoDep` отримують ту саму сесію: знайти й видалити — одна транзакція.

Поруч лишився `DELETE /api/news` з кроку 2 — очистити все; тепер це `DELETE FROM news RETURNING id`, а відповідь — `{"deleted": N}`.

## Пошук: `GET /api/news/search` { #search }

```python title="news_hub/api.py (фрагмент)"
@app.get("/api/news/search", response_model=list[NewsOut], tags=["news"], summary="Пошук у заголовках")
async def search_news(
    repo: RepoDep,
    q: str = Query(min_length=2, max_length=60, description="слово або частина слова"),
    limit: int = Query(20, ge=1, le=100),
) -> list[NewsRow]:
    """Оголошено ДО `/api/news/{news_id}`: інакше «search» потрапив би в news_id і отримав 422."""
    return await repo.search(q, limit)
```

Як пошук побудовано крок за кроком (параметри, SQL, порядок маршрутів) — [розібраний приклад у контрольній точці](checkpoint.md#worked-example).

## Результат: CRUD на справжньому сервері { #result }

PostgreSQL 16, після двох зборів знімка й однієї доданої новини ([розділ 2](repository.md#id-gaps)):

```python
row = api.post("/api/news", json={"title": "НБУ залишив облікову ставку без змін",
                                  "url": "https://www.rbc.ua/ukr/news/nbu-rate-778.html",
                                  "published_time": "14:00"})
news_id = row.json()["id"]
print("POST  ", row.status_code, {key: row.json()[key] for key in ("id", "lang", "category", "published_time")})

again = api.post("/api/news", json={"title": "НБУ залишив облікову ставку без змін",
                                    "url": "https://www.rbc.ua/ukr/news/nbu-rate-778.html"})
print("POST  ", again.status_code, again.json())

patched = api.patch(f"/api/news/{news_id}", json={"category": "Економіка"})
print("PATCH ", patched.status_code, patched.json()["category"], "|", patched.json()["title"])
print("GET   ", api.get(f"/api/news/{news_id}").json()["category"])

deleted = api.delete(f"/api/news/{news_id}")
print("DELETE", deleted.status_code, repr(deleted.text))
missing = api.get(f"/api/news/{news_id}")
print("GET   ", missing.status_code, missing.json())
```

```text
POST   201 {'id': 338, 'lang': 'uk', 'category': 'Новини', 'published_time': '14:00:00'}
POST   409 {'detail': 'новина з url https://www.rbc.ua/ukr/news/nbu-rate-778.html уже є'}
PATCH  200 Економіка | НБУ залишив облікову ставку без змін
GET    Економіка
DELETE 204 ''
GET    404 {'detail': 'новини 338 немає'}
```

- `lang`, `category` і `published_time` у тілі не передавали: їх вивів `NewsItem` з URL і рядка `"14:00"`, як для новин з парсера.
- `PATCH` змінив категорію й не зачепив заголовок.
- `GET` після `PATCH` — **новий запит і нова сесія**, тобто категорія справді в базі, а не лише в пам'яті об'єкта.

Ще три помилки — неправильні дані, неіснуюча новина, `id` не число:

```python
for method, path, body in (("PATCH", "/api/news/1", {"title": "Коротко"}),
                           ("PATCH", "/api/news/999", {"category": "Економіка"}),
                           ("GET", "/api/news/abc", None)):
    response = api.request(method, path, json=body)
    print(method, path, body or "", "→", response.status_code, response.json())
```

```text
PATCH /api/news/1 {'title': 'Коротко'} → 422 {'detail': [{'type': 'string_too_short', 'loc': ['body', 'title'], 'msg': 'String should have at least 10 characters', 'input': 'Коротко', 'ctx': {'min_length': 10}}]}
PATCH /api/news/999 {'category': 'Економіка'} → 404 {'detail': 'новини 999 немає'}
GET /api/news/abc  → 422 {'detail': [{'type': 'int_parsing', 'loc': ['path', 'news_id'], 'msg': 'Input should be a valid integer, unable to parse string as an integer', 'input': 'abc'}]}
```

Зверни увагу на порядок перевірок: `PATCH /api/news/999` з правильним тілом — `404`, бо тіло пройшло перевірку, а `RowDep` не знайшов рядка.

### Дані переживають перезапуск { #persistence }

Новини тепер у базі, а не в процесі сервера. Порахуємо їх **окремою програмою** — без FastAPI, лише через репозиторій (з папки кроку, `DATABASE_URL` — та сама база):

```text
$ python -c "import asyncio; from news_hub.db import SessionFactory; from news_hub.repository import NewsRepository; print(asyncio.run(NewsRepository(SessionFactory()).count()))"
169
```

Зупинили uvicorn (`Ctrl+C`), запустили знову — `GET /api/news/count` повернув `{"count":169}`. Два процеси uvicorn з тим самим `DATABASE_URL` бачать ті самі новини.

### `/docs` і Postman { #docs }

Операції застосунку з кодами відповідей, як їх описує `/openapi.json`:

```text
GET    /health                ['200']
GET    /api/news              ['200', '422']
DELETE /api/news              ['200']
POST   /api/news              ['201', '409', '422']
GET    /api/news/search       ['200', '422']
GET    /api/news/count        ['200']
GET    /api/news/stats        ['200']
POST   /api/scrape            ['200', '422']
GET    /api/news/{news_id}    ['200', '404', '422']
PATCH  /api/news/{news_id}    ['200', '404', '422']
DELETE /api/news/{news_id}    ['204', '404', '422']
```

`409` і `404` потрапили в опис завдяки `responses={...}` в декораторах. Колекція Postman виросла з 7 до 13 запитів: після кроку 2 (запити 1–6) іде сценарій CRUD — «7. створити новину» зберігає `id` у змінну `newsId`, далі «8. та сама новина вдруге» (`409`), «9. змінити категорію», «10. прочитати», «11. видалити» (`204`), «12. вже немає» (`404`), «13. очистити». Усього в колекції 18 перевірок `pm.test`.

## Правило { #rule }

!!! tip "Правило"
    Код відповіді — частина контракту: `201` для створення, `204` для видалення без тіла, `404` — немає ресурсу, `409` — конфлікт зі станом бази, `422` — неправильні дані. Спільну частину ендпоінтів («знайди або `404`») винось у залежність, а в `PATCH` змінюй лише передані поля.

**Далі:** [Міграції Alembic](alembic.md) — звідки в базі береться таблиця `news`.
