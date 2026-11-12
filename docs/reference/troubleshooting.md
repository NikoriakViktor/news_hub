# Типові помилки

Повідомлення → причина → що зробити → де розібрано. Зібрано з розділів «Типові помилки» кроків і частин книги.
Шукай за текстом помилки (`Ctrl+F`) або за кодом відповіді. Що означає кожен код у News Hub —
[Коди відповідей](http_status_codes.md).

## Запуск { #startup }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `Error loading ASGI app. Could not import module "news_hub.api"` | uvicorn запущено не з папки кроку | `cd steps/NN_<тема>`, потім `uvicorn news_hub.api:app` | [крок 2](../tutorials/02_fastapi_basics/checkpoint.md#mistakes) |
| `ModuleNotFoundError: No module named 'news_hub'` | скрипт поза папкою кроку: Python шукає пакети поруч зі скриптом | запускай з папки кроку або `PYTHONPATH=. python шлях/до/скрипт.py` | [крок 1](../tutorials/01_typing_pydantic/checkpoint.md#mistakes), [крок 6](../tutorials/06_ai_dev_tools/checkpoint.md#mistakes) |
| `python api.py` нічого не запускає | `app` — лише об'єкт, сервер — uvicorn | `uvicorn модуль:app` | [Що таке FastAPI](../03_fastapi_core/what_is_fastapi.md#mistakes) |
| `[Errno 98] address already in use` (Windows: `[WinError 10048]`) | порт 8000 зайнятий | `uvicorn … --port 8010` | [крок 2](../tutorials/02_fastapi_basics/checkpoint.md#mistakes) |
| `ValueError: невідомий LLM_PROVIDER: 'gemeni'`, `Application startup failed` | одруківка в назві провайдера | `gemini`, `anthropic` або `fake` | [крок 7](../tutorials/07_llm_api/checkpoint.md#mistakes) |
| `RuntimeError: ADMIN_PASSWORD_HASH — bcrypt-хеш …` | у змінній пароль, а не хеш; або хеш у подвійних лапках — shell з'їв `$2b`, `$12` | `python -m news_hub.security`; хеш — в одинарних лапках | [крок 8](../tutorials/08_security/checkpoint.md#mistakes) |
| `RuntimeError: JWT_SECRET має бути не коротшим за 32 символи` | короткий секрет або задано лише хеш | секрет з `python -m news_hub.security` | [крок 8](../tutorials/08_security/checkpoint.md#mistakes) |
| `RuntimeError: TELEGRAM_WEBHOOK_URL: Telegram надсилає webhook лише на https://` | webhook на `http://` без `TELEGRAM_API_URL` | `https://` на сервері; `http://` — лише з двійником | [крок 9](../tutorials/09_telegram_bot/checkpoint.md#mistakes) |
| `RuntimeError: TELEGRAM_WEBHOOK_SECRET: 32–256 символів …` | секрету немає, він короткий або з пробілом | `python -c 'import secrets; print(secrets.token_urlsafe(48))'` | [крок 9](../tutorials/09_telegram_bot/checkpoint.md#mistakes) |
| `ZoneInfoNotFoundError: 'No time zone found with key Europe/Kyiv'` | у Windows немає бази часових поясів, `tzdata` не встановлено | `pip install -r requirements.txt` (там `tzdata`) | [крок 6](../tutorials/06_ai_dev_tools/checkpoint.md#mistakes) |
| `PydanticImportError` на `from pydantic import BaseSettings` | у Pydantic 2 налаштування — окремий пакет | `pip install pydantic-settings`; `from pydantic_settings import BaseSettings` | [Налаштування](../02_typing_and_pydantic/settings.md#mistakes) |
| `extra_forbidden` при старті `Settings()` | у `.env` чужі ключі (`DOCKER_PORT`), а `extra` за замовчуванням `forbid` | `extra="ignore"` або фільтр за префіксом | [Налаштування](../02_typing_and_pydantic/settings.md#extra) |
| `PydanticUserError: Please use typing_extensions.TypedDict …` | `TypedDict` з `typing` на Python < 3.12 | `from typing_extensions import TypedDict` | [крок 1](../tutorials/01_typing_pydantic/checkpoint.md#mistakes) |
| `AssertionError: A path prefix must not end with '/'` | `APIRouter(prefix="/v1/")` | `prefix="/v1"` | [Версіонування](../01_http_and_rest/versioning.md#mistakes) |

## `422` і перевірка даних { #validation }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `422` на «правильний» запит | параметр не там: модель — у тілі JSON, простий тип — у рядку запиту | дивись `loc`: `["query", …]` чи `["body", …]` | [крок 2](../tutorials/02_fastapi_basics/checkpoint.md#mistakes) |
| `422 Field required` для <code>x: str &#124; None</code> | без `= None` поле обов'язкове (може бути лише `null`) | <code>x: str &#124; None = None</code> | [Анотації типів](../02_typing_and_pydantic/type_hints.md#mistakes) |
| `422` на `/items/stats` | `/items/{id}` оголошено раніше, `"stats"` не `int` | конкретні шляхи першими | [Порядок маршрутів](../03_fastapi_core/routes_and_validation.md#route-order) |
| `422` з `loc: ["header", …]` | обов'язковий `Header()` без значення за замовчуванням | `= None`, якщо заголовок необов'язковий | [HTTP-запит і відповідь](../01_http_and_rest/http_anatomy.md#mistakes) |
| `422` з `loc: ["body", 0]`, `json_invalid` | тіло — не JSON (зайва кома, одинарні лапки, `curl -d` без `Content-Type`) | перевір тіло; `-H 'Content-Type: application/json'` | [Архітектура](architecture.md#di) |
| `extra_forbidden`, `Extra inputs are not permitted` | у тілі поле, якого немає в моделі з `extra="forbid"` | прибрати поле або змінити `extra` | [`ConfigDict`](../02_typing_and_pydantic/config_dict.md#extra) |
| `422` на `PATCH` з `{"title": null}` у News Hub | `NewsPatch` забороняє явний `null` | не змінюєш поле — не передавай його | [Моделі Pydantic](../02_typing_and_pydantic/pydantic_models.md#mistakes) |
| правильні запити → `422` після `strict=True` | strict не перетворює рядки JSON на `date`, `UUID`, `Decimal` | strict точково: `StrictInt`, `StrictBool` | [lax і strict](../02_typing_and_pydantic/strict_mode.md#mistakes) |
| тіло стало query-параметром | модель оголошено всередині функції з `from __future__ import annotations` | моделі — на рівні модуля | [Анотації типів](../02_typing_and_pydantic/type_hints.md#mistakes) |

## `500` і відповіді { #responses }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `ResponseValidationError` з `'loc': ('response', 'id')`, `'input': None` | об'єкт повернули до `flush()`: `INSERT` ще не було | `await session.flush()` після `add` | [крок 3](../tutorials/03_sqlalchemy_alembic/session_per_request.md#flush) |
| `ResponseValidationError` на `AwareDatetime` | SQLite повертає naive `datetime` | `datetime` у моделі відповіді або тести на PostgreSQL | [Дати](../02_typing_and_pydantic/special_types.md#aware-response) |
| `ResponseValidationError` / `get_attribute_error` з `MissingGreenlet` | лінивий зв'язок SQLAlchemy читається поза `await` (Pydantic звертається до атрибута) | `selectinload(...)` у запиті; `lazy="raise"`, щоб помилка була явною | [`from_attributes`](../02_typing_and_pydantic/config_dict.md#from-attributes) |
| `DetachedInstanceError` у відповіді | об'єкт вийшов за межі сесії, а атрибут не завантажено | завантажити до закриття сесії | [`from_attributes`](../02_typing_and_pydantic/config_dict.md#from-attributes) |
| `500` замість `422` після `model_validate` у маршруті | `ValidationError` у твоєму коді — це помилка сервера | `try` → `HTTPException(422, ...)` або модель у сигнатурі | [`ValidationError`](../02_typing_and_pydantic/validation_error.md#inside-route) |
| `500` у власному обробнику `422` | `exc.errors()` з `ctx` (`ValueError`) не серіалізується в JSON | `include_context=False` або `jsonable_encoder` | [`ValidationError`](../02_typing_and_pydantic/validation_error.md#mistakes) |
| `TypeError: Object of type HttpUrl is not JSON serializable` | `json.dumps(item.model_dump())` | `model_dump(mode="json")` або `model_dump_json()` | [крок 1](../tutorials/01_typing_pydantic/checkpoint.md#mistakes) |
| `201`, хоча `COMMIT` упав | `Depends(get_db)` без `scope="function"`: `COMMIT` після відповіді | `Depends(get_db, scope="function")` | [Сесія на запит](../tutorials/03_sqlalchemy_alembic/session_per_request.md#scope) |
| `TypeError: Depends() got an unexpected keyword argument 'scope'` | FastAPI старіший за 0.121 | підняти нижню межу в `requirements.txt` | [крок 12](../tutorials/12_ci_cd/checkpoint.md#mistakes) |
| `200` з `{"error": "…"}` | помилку повернули словником | `raise HTTPException(404, …)` | [Коди відповідей](../01_http_and_rest/status_codes.md#mistakes) |
| `500`, а дублікат — вина клієнта | необроблений `IntegrityError` | `except IntegrityError` → `409` | [Коди відповідей](../01_http_and_rest/status_codes.md#mistakes) |

## База й міграції { #database }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `sqlite3.OperationalError: no such table: news` | міграції не застосовано (`lifespan` таблиць не створює) | `alembic upgrade head` з тим самим `DATABASE_URL` | [крок 3](../tutorials/03_sqlalchemy_alembic/checkpoint.md#mistakes) |
| `no such column: news.summary` | база на старій ревізії | `alembic upgrade head` | [крок 7](../tutorials/07_llm_api/checkpoint.md#mistakes) |
| `FAILED: No 'script_location' key found in configuration.` | `alembic` не з папки кроку | `cd steps/NN_<тема>` | [крок 3](../tutorials/03_sqlalchemy_alembic/checkpoint.md#mistakes) |
| `ConnectionRefusedError: … ('127.0.0.1', 5432)` | PostgreSQL не запущено або інший порт | `docker compose up -d db`; перевір `DATABASE_URL` | [крок 3](../tutorials/03_sqlalchemy_alembic/checkpoint.md#mistakes) |
| міграції пройшли, а сервер «не бачить» новин | `DATABASE_URL` задано лише в одному терміналі | задай в обох; без нього — файл `news_hub.db` у поточній папці | [крок 3](../tutorials/03_sqlalchemy_alembic/checkpoint.md#mistakes) |
| `OperationalError unknown function: now()` на SQLite | автоміграція з `server_default=sa.text('now()')` | `sa.func.now()` | [Міграції](../tutorials/03_sqlalchemy_alembic/alembic.md#autogenerate) |
| `FAILED: New upgrade operations detected` у CI | змінено `tables.py` без міграції | `alembic revision --autogenerate -m "…"`, прочитати міграцію | [крок 12](../tutorials/12_ci_cd/checkpoint.md#mistakes) |
| пошук кирилицею на SQLite нічого не знаходить | вбудований `lower()` SQLite не знає кирилиці | engine через `make_engine` (реєструє `_unicode_lower`) | [крок 3](../tutorials/03_sqlalchemy_alembic/checkpoint.md#mistakes) |
| `500 no such table` з `sqlite:///:memory:` і `def`-ендпоінтами | кожен потік пулу отримує свою порожню базу | `poolclass=StaticPool` або файл | [Методи HTTP](../01_http_and_rest/http_methods.md#mistakes) |
| `InterfaceError: cannot rollback; the transaction is already committed` | Unit of Work з asyncpg викликає `rollback()` після `commit()` | відкочувати лише незакомічену транзакцію | [Архітектура](architecture.md#uow) |

## Redis, кеш, ліміти { #redis }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `/health` → `200`, а `/api/news` → `500`; `Error 111 connecting to localhost:6379` | Redis не запущений (клієнт підключається з першою командою) | `docker compose up -d redis` або `REDIS_URL=fakeredis://` | [крок 4](../tutorials/04_middleware_redis/checkpoint.md#mistakes) |
| `429` у Swagger після експериментів | 5 зборів за 60 с з твоєї адреси | зачекати `Retry-After` або `redis-cli DEL rate:scrape:127.0.0.1` | [крок 4](../tutorials/04_middleware_redis/checkpoint.md#mistakes) |
| `429 забагато запитів: 5 за 300 с` на правильний пароль | ліміт входу рахує всі спроби | зачекати; для розробки — більший `LOGIN_RATE_LIMIT` | [крок 8](../tutorials/08_security/checkpoint.md#mistakes) |
| `429 забагато невдалих входів під цим іменем; спробуй через N с` на правильний пароль | `LOGIN_FAIL_LIMIT` (20) невдалих входів під цим іменем за `LOGIN_FAIL_WINDOW` (900 с) — з будь-яких адрес разом; хтось підбирає пароль або сам помилявся | зачекати `Retry-After`; якщо це атака — вона й закрила вхід; скинути: `redis-cli DEL login:fail:<перші 32 символи sha256 імені в нижньому регістрі>` | [Ліміт входу за ім'ям](../08_security/secrets_and_headers.md#news-hub-fixes) |
| API показує старі дані після зміни в базі напряму | кеш не знає про записи в обхід API | зачекати TTL (60 с) або `redis-cli INCR news:version` | [крок 4](../tutorials/04_middleware_redis/checkpoint.md#mistakes) |
| у тестах задача одразу `done`, на сервері — `queued` | `TestClient` чекає на фонові задачі, сервер — ні | на сервері опитувати статус | [крок 4](../tutorials/04_middleware_redis/checkpoint.md#mistakes) |
| усі клієнти ділять один ліміт `rate:login:<адреса nginx>` | uvicorn не вірить `X-Forwarded-For` від nginx | `FORWARDED_ALLOW_IPS` = `ipv4_address` nginx | [крок 11](../tutorials/11_compose_deploy/checkpoint.md#mistakes) |

## Тести { #tests }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `AttributeError: 'State' object has no attribute 'store'` | `TestClient(app)` без `with` — `lifespan` не запустився | `with TestClient(app) as client:` | [крок 2](../tutorials/02_fastapi_basics/checkpoint.md#mistakes) |
| `'State' object has no attribute 'redis'` в async-тесті | `ASGITransport` не запускає `lifespan` | `async with app.router.lifespan_context(app):` | [крок 5](../tutorials/05_api_testing/checkpoint.md#mistakes) |
| `async def functions are not natively supported` | немає `@pytest.mark.asyncio` або `pytest-asyncio` | маркер; `pip install -r requirements.txt` | [крок 5](../tutorials/05_api_testing/checkpoint.md#mistakes) |
| `Expected 'parse_rbc_news' to be called once. Called 0 times.` | патч там, де функцію визначено, а не де її шукають | `mock.patch("news_hub.scraper.parse_rbc_news")` | [крок 5](../tutorials/05_api_testing/mock_network.md) |
| `PytestUnknownMarkWarning: Unknown pytest.mark.unit` | маркер не оголошено | `markers = …` у `pytest.ini` | [крок 5](../tutorials/05_api_testing/checkpoint.md#mistakes) |
| `pytest -m unitt` → усе `deselected` | одруківка: `-m` не перевіряється | `pytest --markers` | [крок 5](../tutorials/05_api_testing/checkpoint.md#mistakes) |
| покриття занижене на рядках сесії | coverage не бачить greenlet async SQLAlchemy | `concurrency = thread,greenlet` у `.coveragerc` | [крок 5](../tutorials/05_api_testing/coverage.md) |
| підміна з одного тесту діє в інших | не очищено `dependency_overrides` | `.clear()` у фікстурі після `yield` | [Залежності](../03_fastapi_core/dependencies.md#mistakes) |
| `RuntimeError: Router is already attached to <Dispatcher …>` | роутер aiogram — змінна модуля, а диспетчерів два | новий роутер на кожен диспетчер: `build_router()` | [крок 9](../tutorials/09_telegram_bot/checkpoint.md#mistakes) |
| `test_runs_as_non_root_and_cannot_change_code`: `assert 0 != 0` | образ зібрано з `/mnt/c` у WSL: файли `rwxrwxrwx` | збирати з клону на файловій системі Linux | [крок 12](../tutorials/12_ci_cd/checkpoint.md#mistakes) |

## LLM { #llm }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `503 LLM не налаштовано: задай GEMINI_API_KEY …` | немає ключа (для Anthropic — ще й `ANTHROPIC_MODEL`) | ключ або `LLM_PROVIDER=fake` | [крок 7](../tutorials/07_llm_api/checkpoint.md#mistakes) |
| `502 … gemini відхилив запит (400): API key not valid` | невалідний ключ (Gemini відповідає `400`) | перевір ключ; після 5 збоїв breaker вимикає аналіз на 300 с | [крок 7](../tutorials/07_llm_api/checkpoint.md#mistakes) |
| `503 … спробуй через 300 с` після виправлення ключа | breaker ще відкритий (`cb:llm:open` у Redis) | зачекати `Retry-After` або видалити ключ локально | [Circuit breaker](../tutorials/07_llm_api/circuit_breaker.md) |
| змінив промпт — відповіді старі | кеш за хешем тексту з `PROMPT_VERSION` | збільшити `PROMPT_VERSION` | [крок 7](../tutorials/07_llm_api/db_cache_cost.md) |

## Безпека й webhook { #security }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `503 адмін-доступ не налаштовано` | змінні задано в іншому терміналі чи після старту | `export …` у тому самому shell і перезапуск | [крок 8](../tutorials/08_security/checkpoint.md#mistakes) |
| `401 токен прострочений` | токен живе `JWT_EXPIRE_MINUTES` (30) хвилин | увійти знову | [крок 8](../tutorials/08_security/checkpoint.md#mistakes) |
| `400 заборонена адреса: … loopback` / `порт 8080` | `safe_fetch` ходить лише в публічний інтернет на 80/443 | у тестах — своя `FetchPolicy` через `dependency_overrides` | [SSRF](../tutorials/08_security/ssrf.md) |
| webhook → `401 підпис не збігається` | підписано одні байти, надіслано інші | підписувати рівно те тіло, що надсилаєш | [Підписані webhook](../tutorials/08_security/webhooks.md) |
| webhook → `401 запит старший за 300 с` | годинник відправника розійшовся більш ніж на 5 хв | NTP; підписувати перед надсиланням | [Підписані webhook](../tutorials/08_security/webhooks.md) |
| webhook → `401 X-Webhook-Delivery: 8–64 символи A-Z a-z 0-9 _ -` | немає заголовка id доставки або id закороткий чи з іншими символами | `X-Webhook-Delivery: <uuid4().hex>`, той самий id — у підписі `"<t>.<id>." + body` | [Webhook у News Hub](../08_security/webhooks_and_signatures.md#news-hub) |
| webhook → `200` замість `202`, новий збір не запустився | той самий `X-Webhook-Delivery`, що й у вже прийнятої доставки: це повтор, відповідь — вже наявне завдання | нова подія — новий id; повтор після тайм-ауту — з тим самим id (так і задумано) | [Повтор доставки](../08_security/webhooks_and_signatures.md#news-hub-replay) |
| webhook → `409 ця доставка ще обробляється` | дві доставки з одним id одночасно: перша ще не створила завдання | повторити за секунду — буде `200` з тим самим завданням | [Повтор доставки](../08_security/webhooks_and_signatures.md#news-hub-replay) |

## CORS { #cors }

| Повідомлення браузера | Причина | Що зробити | Де |
|---|---|---|---|
| `No 'Access-Control-Allow-Origin' header is present` | джерело не збіглося (зайвий `/` у кінці, інший порт чи схема) | точне джерело: `https://ui.example.com` | [CORS](../06_middleware_cache_jobs/cors.md#mistakes) |
| «CORS error» на запит, що впав | `500` завжди без заголовків CORS | дивитися журнал сервера | [CORS](../06_middleware_cache_jobs/cors.md#errors) |
| `429`/`401` без заголовків CORS | middleware додано після `CORSMiddleware` (він не зовнішній) | `CORSMiddleware` — останнім | [CORS](../06_middleware_cache_jobs/cors.md#mistakes) |
| `X-Request-ID` не видно у `fetch` | скрипт бачить лише стандартні заголовки | `expose_headers=["X-Request-ID"]` | [CORS](../06_middleware_cache_jobs/cors.md#mistakes) |

## Telegram { #telegram }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `Задай BOT_TOKEN …`, код 1 | `python -m news_hub.bot` без токена | токен або двійник з `TELEGRAM_API_URL` | [крок 9](../tutorials/09_telegram_bot/checkpoint.md#mistakes) |
| `TelegramBadRequest: … can't parse entities` | чужий текст у HTML без екранування | `esc` / `link` | [Відповідь у HTML](../tutorials/09_telegram_bot/html_replies.md) |
| `409 Conflict: can't use getUpdates method while webhook is active` | webhook увімкнено, а запущено polling | один токен — один режим | [Polling і webhook](../tutorials/09_telegram_bot/polling_webhook.md) |
| `POST /api/telegram/webhook` → `503` | немає `BOT_TOKEN` або `TELEGRAM_WEBHOOK_URL` / секрету | так і має бути в режимі polling | [крок 9](../tutorials/09_telegram_bot/checkpoint.md#mistakes) |
| `RuntimeError: BOT_ADMIN_IDS задано, а адмін-доступ — ні: …` при старті | адміни бота — частина адмін-налаштувань API, а `JWT_SECRET` і `ADMIN_PASSWORD_HASH` не задано | задати обидва або прибрати `BOT_ADMIN_IDS` | [Два входи, одне правило](../08_security/authorization.md#news-hub-two-entries) |
| `RuntimeError: BOT_ADMIN_IDS — числові id Telegram через кому, …` | у списку `@username`, `chat_id` групи з літерами чи інший символ | числові id користувачів: `1001,2002` | [Змінні середовища](env_vars.md#security) |
| бот: `Забагато зборів: 5 за 60 с; спробуй через T с.` | `/scrape` має ту саму межу, що й `POST /api/scrape*` (`RATE_LIMIT_REQUESTS` за `RATE_LIMIT_WINDOW`), окремий лічильник на кожного адміна | зачекати; для розробки — більший `RATE_LIMIT_REQUESTS` | [Два входи, одне правило](../08_security/authorization.md#news-hub-two-entries) |

## Docker { #docker }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `unable to open database file` при `alembic upgrade head` у контейнері | база в `/app`, а користувач `app` там писати не може | `DATABASE_URL` на `/data` і `-v news_data:/data` | [крок 10](../tutorials/10_docker/checkpoint.md#mistakes) |
| `"redis":"ConnectionError"`, `connecting to localhost:6379` | `localhost` у контейнері — сам контейнер | `REDIS_URL=redis://redis:6379/0` у спільній мережі | [крок 10](../tutorials/10_docker/checkpoint.md#mistakes) |
| `Connection refused` на `localhost:8000` з комп'ютера | немає `-p 8000:8000` або uvicorn слухає `127.0.0.1` | `-p 8000:8000`, `--host 0.0.0.0` | [крок 10](../tutorials/10_docker/checkpoint.md#mistakes) |
| `Exited (3)`, `RuntimeError: ADMIN_PASSWORD_HASH …` з `--env-file` | у `--env-file` значення взято разом з лапками | `python -m news_hub.security --env-file` | [крок 10](../tutorials/10_docker/checkpoint.md#mistakes) |
| `docker stop` триває 10 с, `exit 137` | shell-форма `CMD`: `SIGTERM` отримує `/bin/sh` | exec-форма `CMD ["uvicorn", …]` | [крок 10](../tutorials/10_docker/health_shutdown.md) |
| `.env` або `.venv` в образі | їх немає в `.dockerignore` | додати; ключі, що потрапили в образ, — замінити | [крок 10](../tutorials/10_docker/image_contents.md) |
| кожне збирання ставить усі залежності | `COPY . .` перед `pip install` | спершу `COPY requirements.txt .` + `pip install` | [Шари й кеш](../tutorials/10_docker/layers_cache.md) |

## Compose і деплой { #compose }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `failed to create network …_edge: … Pool overlaps with other one on this address space` | інша мережа Docker уже займає `172.28.0.0/…` | знайти: `docker network inspect $(docker network ls -q) --format '{{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}'`; змінити `subnet`, `ipv4_address` і `FORWARDED_ALLOW_IPS` разом | [крок 11](../tutorials/11_compose_deploy/checkpoint.md#mistakes) |
| `required variable POSTGRES_PASSWORD is missing a value` | немає `.env` або пароль порожній | `cp .env.example .env` і заповнити | [крок 11](../tutorials/11_compose_deploy/checkpoint.md#mistakes) |
| `The "pVoAkKpIgbdK5I" variable is not set. Defaulting to a blank string.` | значення з `$` у `.env` без лапок | одинарні лапки: `ADMIN_PASSWORD_HASH='$2b$12$…'` | [Секрети в `.env`](../tutorials/11_compose_deploy/env_secrets.md) |
| `container …-api-1 is unhealthy` | `docker compose logs api`: часто обрізаний хеш | `python -m news_hub.security`, рядки як надруковано | [крок 11](../tutorials/11_compose_deploy/checkpoint.md#mistakes) |
| `service "migrate" didn't complete successfully: exit 255` | міграція впала | `docker compose logs migrate` | [крок 11](../tutorials/11_compose_deploy/checkpoint.md#mistakes) |
| `Bind for 0.0.0.0:80 failed: port is already allocated` | порт 80 зайнятий | `HTTP_PORT=8080` у `.env` | [крок 11](../tutorials/11_compose_deploy/checkpoint.md#mistakes) |
| `/docs` і `/openapi.json` → `404` на сервері, а локально працюють | Compose ставить `DOCS_ENABLED: ${DOCS_ENABLED:-false}` | так і задумано; тимчасово — `DOCS_ENABLED=true` у `.env` і `docker compose up -d api` | [Заголовки й `/docs`](../08_security/secrets_and_headers.md#news-hub-fixes) |
| nginx перші секунди відповідає `502` | `depends_on` без `condition: service_healthy` | `condition: service_healthy` | [Порядок запуску](../tutorials/11_compose_deploy/startup_order.md) |
| `"database":"ConnectionRefusedError"` при `(healthy)` | `localhost` у `DATABASE_URL` усередині контейнера | `@postgres:5432` | [крок 11](../tutorials/11_compose_deploy/checkpoint.md#mistakes) |
| `./scripts/backup.sh`: `service "postgres" is not running` | стек запущено з `-p <ім'я>` | `COMPOSE_PROJECT_NAME=<ім'я> ./scripts/backup.sh` | [Бекап](../tutorials/11_compose_deploy/backup_restore.md) |

## CI { #ci }

| Повідомлення | Причина | Що зробити | Де |
|---|---|---|---|
| `./scripts/smoke.sh: Permission denied` (код 126) | файл з NTFS (`core.filemode=false`): у git-індексі немає біта виконання | `git update-index --chmod=+x steps/12_ci_cd/scripts/smoke.sh` | [крок 12](../tutorials/12_ci_cd/checkpoint.md#mistakes) |
| `ADMIN_PASSWORD: задай ADMIN_PASSWORD …` | smoke без змінної | `ADMIN_PASSWORD=… ./scripts/smoke.sh` | [крок 12](../tutorials/12_ci_cd/checkpoint.md#mistakes) |
| `.env уже є — не чіпаю`, код 1 | `make_env.py` не перезаписує `.env` | видалити старий `.env` або взяти його пароль | [крок 12](../tutorials/12_ci_cd/checkpoint.md#mistakes) |
| `JSONDecodeError: Expecting value` після `✓ nginx відповідає` | пароль не той: `/api/admin/token` → `401`, `curl -sf` дав порожнє тіло | правильний пароль або новий `.env` | [крок 12](../tutorials/12_ci_cd/checkpoint.md#mistakes) |
| PR без перевірки `news_hub — CI/CD` | змінено лише файли поза `paths` | так і має бути для `docs/` | [Коли CI запускається](../tutorials/12_ci_cd/triggers.md) |
| обов'язкова перевірка «очікує» вічно | workflow з `paths` не стартував, а перевірка required | required — лише перевірки, що йдуть на кожен PR | [крок 12](../tutorials/12_ci_cd/checkpoint.md#mistakes) |
| `✗ база й Redis без портів назовні` | у `docker-compose.yml` для `postgres`/`redis` додано `ports` | порти — лише в `docker-compose.dev.yml` | [крок 12](../tutorials/12_ci_cd/checkpoint.md#mistakes) |
| job «залежності й секрети»: `git diff --exit-code -- requirements.lock` падає, у diff — нові пакети | `requirements.txt` змінено, а `requirements.lock` не перегенеровано | у `steps/12_ci_cd`: `uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock` і закомітити обидва файли | [Supply chain у News Hub](../08_security/owasp_api_top10.md#owasp-top10-2025) |
| той самий job: `pip-audit` знайшов вразливість | у версії з lock є відома CVE (база PyPA) | підняти нижню межу в `requirements.txt` (або `uv pip compile … --upgrade-package <пакет>`), перегенерувати lock | [Supply chain у News Hub](../08_security/owasp_api_top10.md#owasp-top10-2025) |
| той самий job: gitleaks знайшов секрет | у якомусь коміті історії — схоже на ключ чи токен | справжній секрет — **замінити** (видалення з історії не скасовує витоку); навчальне значення — точним рядком в allowlist `.gitleaks.toml` | [Секрети в git](../08_security/secrets_and_headers.md#debugging) |
| образ кроку 12: `ModuleNotFoundError` на щойно доданий пакет | Dockerfile ставить `requirements.lock` (`--require-hashes`), а не `requirements.txt` | перегенерувати lock (рядок вище) | [Supply chain у News Hub](../08_security/owasp_api_top10.md#owasp-top10-2025) |
