# FastAPI, Flask і Django

## Проблема { #problem }

У Python три популярні вебфреймворки, і порівняння в інтернеті часто зводяться до «FastAPI найшвидший». Але обирають не за швидкістю. Важливіше, **що фреймворк робить за тебе**: хто перевіряє вхідні дані, звідки береться документація API, чи є база й адмінка, як влаштована асинхронність. Найпростіше це побачити на одному й тому самому API, написаному трьома способами.

## Ментальна модель { #mental-model }

Три фреймворки — три відповіді на питання «скільки рішень прийняти за розробника».

| | Django | Flask | FastAPI |
|---|---|---|---|
| Рік, автор | 2005 (внутрішньо — з 2003), Lawrence Journal-World | 2010, Армін Ронахер | 2018, Себастьян Рамірес |
| Підхід | «батарейки в комплекті»: ORM, міграції, адмінка, автентифікація, шаблони, форми | мікрофреймворк: маршрути, запит/відповідь, шаблони Jinja2; решту обираєш сам | фреймворк саме для API: типи Python → перевірка, серіалізація, документація |
| На чому стоїть | власний стек | Werkzeug (WSGI) + Jinja2 | Starlette (ASGI) + Pydantic |
| Протокол сервера | WSGI; ASGI — з 3.0 | WSGI | ASGI |
| Маршрути | таблиця URLConf (`urlpatterns`) | декоратори `@app.route`, з 2.0 — `@app.get` | декоратори `@app.get`, `@app.post` |
| Перевірка даних | `forms.Form`, валідатори моделей; для API — DRF або Django Ninja | вручну або бібліотекою (marshmallow, Pydantic) | Pydantic з анотацій, помилка — `422` |
| OpenAPI і `/docs` | немає; пакети drf-spectacular або Ninja | немає; пакети на кшталт flask-smorest | є з коробки: `/openapi.json`, `/docs`, `/redoc` |
| Впровадження залежностей | немає | немає (є `g`, `current_app`) | `Depends` |
| База даних | вбудований ORM + міграції + адмінка | немає: зазвичай SQLAlchemy (Flask-SQLAlchemy) | немає: SQLAlchemy або SQLModel (від автора FastAPI) |

## Той самий API трьома способами { #same-api }

Код — [`examples/frameworks_compared`](https://github.com/NikoriakViktor/news_hub/tree/main/examples/frameworks_compared). Правила однакові: `title` — рядок від 1 до 200 символів, `priority` — ціле від 1 до 4, `limit` — ціле від 1 до 100.

=== "FastAPI"

    ```python title="fastapi_app.py"
    class NoteIn(BaseModel):
        title: str = Field(min_length=1, max_length=200)
        priority: int = Field(1, ge=1, le=4)


    @app.get("/api/notes")
    def list_notes(limit: int = Query(10, ge=1, le=100)) -> list[dict]:
        return NOTES[:limit]


    @app.post("/api/notes", status_code=201)
    def create_note(note: NoteIn) -> dict:
        NOTES.append({"id": len(NOTES) + 1, **note.model_dump()})
        return NOTES[-1]
    ```

    Правила записано в типах. До тіла функції доходять лише перевірені дані.

=== "Flask"

    ```python title="flask_app.py"
    @app.get("/api/notes")
    def list_notes():
        limit = request.args.get("limit", 10, type=int)   # «abc» → тихо стане 10
        if not 1 <= limit <= 100:
            return jsonify(error="limit: від 1 до 100"), 400
        return jsonify(NOTES[:limit])


    @app.post("/api/notes")
    def create_note():
        data = request.get_json(silent=True) or {}
        errors = {}
        title = data.get("title")
        if not isinstance(title, str) or not 1 <= len(title) <= 200:
            errors["title"] = "рядок від 1 до 200 символів"
        priority = data.get("priority", 1)
        if not isinstance(priority, int) or not 1 <= priority <= 4:
            errors["priority"] = "ціле від 1 до 4"
        if errors:
            return jsonify(errors=errors), 400
        NOTES.append({"id": len(NOTES) + 1, "title": title, "priority": priority})
        return jsonify(NOTES[-1]), 201
    ```

    Дані дістаються з `request` вручну, кожне правило — `if`. Формат помилки вигадуєш сам.

=== "Django"

    ```python title="django_app.py (скорочено)"
    class NoteForm(forms.Form):
        title = forms.CharField(min_length=1, max_length=200)
        priority = forms.IntegerField(min_value=1, max_value=4, required=False)


    @csrf_exempt
    @require_http_methods(["GET", "POST"])
    def notes(request):
        if request.method == "GET":
            form = LimitForm(request.GET)
            if not form.is_valid():
                return JsonResponse({"errors": form.errors}, status=400)
            return JsonResponse(NOTES[: form.cleaned_data["limit"] or 10], safe=False)
        form = NoteForm(json.loads(request.body or b"{}"))
        if not form.is_valid():
            return JsonResponse({"errors": form.errors}, status=400)
        ...


    urlpatterns = [path("api/notes", notes)]      # маршрути — таблицею, а не декораторами
    ```

    Правила — у класі форми, як для HTML-форм. JSON, методи й CSRF — вручну. Для справжнього API в Django беруть DRF ([наступна сторінка](fastapi_vs_drf.md)) або Django Ninja.

## Ті самі запити — різні відповіді { #results }

`compare.py` надсилає однакові запити всім трьом через їхні тестові клієнти:

```text
POST добра
  FastAPI  201  {"id": 1, "title": "Купити каву", "priority": 2}
  Flask    201  {"id": 1, "priority": 2, "title": "Купити каву"}
  Django   201  {"id": 1, "title": "Купити каву", "priority": 2}
POST погана  {"title": "", "priority": 9}
  FastAPI  422  [(['body', 'title'], 'String should have at least 1 character'), (['body', 'priority'], 'Input should be less than or equal to 4')]
  Flask    400  {"errors": {"priority": "ціле від 1 до 4", "title": "рядок від 1 до 200 символів"}}
  Django   400  {"errors": {"title": ["This field is required."], "priority": ["Ensure this value is less than or equal to 4."]}}
GET limit=abc
  FastAPI  422  [(['query', 'limit'], 'Input should be a valid integer, unable to parse string as an integer')]
  Flask    200  [{"id": 1, "priority": 2, "title": "Купити каву"}]
  Django   400  {"errors": {"limit": ["Enter a whole number."]}}
GET limit=1
  FastAPI  200  [{"id": 1, "title": "Купити каву", "priority": 2}]
  Flask    200  [{"id": 1, "priority": 2, "title": "Купити каву"}]
  Django   200  [{"id": 1, "title": "Купити каву", "priority": 2}]
OpenAPI:
  FastAPI  200 ['/api/notes']
  Flask    404
  Django   404
```

(Для FastAPI замість повного `detail` показано пари `loc` і `msg`.)

Що тут видно:

- **Flask на `limit=abc` відповів `200`.** `request.args.get(..., type=int)` при помилці перетворення мовчки повертає значення за замовчуванням. Клієнт помилився, а дізнатися про це йому нема як. Рядок коду виглядає правильно, але правило «неправильний параметр → помилка» він не виконує.
- **Django назвав порожній `title` відсутнім.** Для `CharField` порожній рядок означає «поле не заповнили», тому повідомлення — «This field is required», а не «закороткий». Логіка HTML-форм, а не API.
- **FastAPI** — `422` і список помилок з місцем кожної (`body.title`, `query.limit`). Цей формат однаковий для всіх ендпоінтів і описаний у схемі API.
- **OpenAPI** є лише у FastAPI. У Flask і Django `/openapi.json` — `404`, поки не підключиш окремий пакет.

## Асинхронність: ASGI і WSGI { #async }

**WSGI** (Flask, класичний Django) — один запит займає один потік або процес від початку до кінця. Поки обробник чекає базу чи інший сайт, потік стоїть. **ASGI** (FastAPI, Django з 3.0) — сервер і застосунок спілкуються через `async`, і один потік циклу подій обслуговує багато запитів, які чекають на мережу.

- **FastAPI:** `async def` виконується в циклі подій, звичайний `def` — у пулі потоків, тож блокуючий код у `def` цикл не зупиняє ([як це працює](what_is_fastapi.md#inside)). Блокуючий виклик усередині `async def` зупиняє весь сервер. Виміри цього — на [кроці 2](../tutorials/02_fastapi_basics/async_measurements.md).
- **Flask** з 2.0 приймає `async def`-обробники (пакет `flask[async]`), але лишається WSGI: кожен такий запит отримує власний цикл подій у робочому потоці. Конкурентність це не збільшує, лише дозволяє викликати async-бібліотеки. ASGI-версія Flask — окремий фреймворк Quart.
- **Django:** ASGI — з 3.0, async-представлення — з 3.1, async-методи ORM (`aget`, `acreate`, `async for`) — з 4.1. Частина ORM усередині досі виконується в потоках (`sync_to_async`).

**Про швидкість.** FastAPI швидкий серед Python-фреймворків, і в синтетичних тестах він близький до Node.js і Go. Але в реальному API час відповіді зазвичай визначають база, мережа й зовнішні сервіси, а не фреймворк. Тому вибір фреймворку заради швидкості рідко щось вирішує, а правильна асинхронність там, де багато очікування I/O, — вирішує.

## Як обрати { #how-to-choose }

| Задача | Що брати | Чому |
|---|---|---|
| сайт з HTML-сторінками, адмінкою, користувачами | Django | усе це вже є і узгоджене між собою |
| API над наявним Django-проєктом | Django + DRF або Ninja | ті самі моделі, права й адмінка |
| окремий API-сервіс: багато I/O, інтеграції, ML | FastAPI | типи → перевірка й документація, async, `Depends` |
| маленький сервіс, вебхук, внутрішній інструмент на кілька сторінок | Flask або FastAPI | мінімум коду; Flask — якщо потрібні шаблони й знайомий стек |
| API, де важлива контрактна документація для інших команд | FastAPI | OpenAPI генерується з коду і не відстає від нього |

News Hub — третій рядок: окремий сервіс, який постійно ходить у мережу (сайти, LLM, Telegram), без HTML-сторінок і адмінки.

## Типові помилки { #mistakes }

| Помилка | Наслідок | Як правильно |
|---|---|---|
| обирати FastAPI «бо швидкий», а писати блокуючий код в `async def` | один повільний запит зупиняє весь сервер | блокуюче — у `def` або `run_in_threadpool`; async-бібліотеки (`httpx`, `asyncpg`) |
| `request.args.get(..., type=int)` у Flask як перевірка | неправильний параметр мовчки стає значенням за замовчуванням | явна перевірка або Pydantic / marshmallow |
| Django `forms.Form` для JSON API | помилки у форматі HTML-форм, CSRF, ручний JSON | DRF або Django Ninja |
| очікувати від FastAPI ORM, адмінку, вхід користувачів | їх немає | SQLAlchemy + Alembic ([Частина V](../05_databases/README.md)), JWT ([Частина VIII](../08_security/README.md)) |

## Питання { #questions }

1. Чому Flask на `?limit=abc` повернув `200`, а не помилку?
2. Що FastAPI бере з анотації `limit: int = Query(10, ge=1, le=100)`?
3. Чи робить `async def` у Flask сервер здатним обслуговувати більше одночасних запитів?
4. Що обрати для API, який віддає прогнози ML-моделі й нічого більше, і чому?

??? success "Відповіді"

    1. `request.args.get(..., type=int)` ловить помилку перетворення і повертає значення за замовчуванням (10).
    2. Тип (ціле), джерело (рядок запиту), значення за замовчуванням і межі. З цього — перевірка з `422`, перетворення рядка на `int` і опис параметра в OpenAPI.
    3. Ні: Flask лишається WSGI, кожен async-запит займає робочий потік і отримує власний цикл подій.
    4. FastAPI: окремий API без сторінок і адмінки; перевірка вхідних даних і `/docs` з коробки.

## Що далі { #next }

[FastAPI і Django REST Framework](fastapi_vs_drf.md) — та сама порівняльна вправа, але з DRF, тобто з повноцінним API-шаром Django.

**Джерела:** [FastAPI — Alternatives, Inspiration and Comparisons](https://fastapi.tiangolo.com/alternatives/); [FastAPI — Concurrency and async / await](https://fastapi.tiangolo.com/async/); [Flask — Using async and await](https://flask.palletsprojects.com/en/stable/async-await/); [Django — Asynchronous support](https://docs.djangoproject.com/en/stable/topics/async/); [Django — URL dispatcher](https://docs.djangoproject.com/en/stable/topics/http/urls/).
