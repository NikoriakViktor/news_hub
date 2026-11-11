# Промпти для RAG: наповнення книги FastAPI

Робочий файл автора, на сайт книги не потрапляє (`exclude_docs: _internal/`).

Мета — витягти з RAG-моделі (індекс документації FastAPI, Starlette, Pydantic, SQLAlchemy, Alembic, Redis, pytest,
HTTPX, aiogram, Docker, GitHub Actions) **факти з посиланнями**. Ці факти потім перевіряються кодом у `steps/` і стають
розділами книги за шаблоном: проблема → ментальна модель → як працює всередині → мінімальний приклад → News Hub →
типові помилки → налагодження → безпека → питання.

## Як користуватися

1. Перед кожним промптом — **системна інструкція** нижче.
2. Відповідь RAG — сировина, а не текст книги. Кожен приклад коду запустити (venv кроку, версії з `requirements.txt`),
   у книгу — лише реальний вивід.
3. Що не підтвердилося запуском або документацією — не переносити.
4. Позначати `[x]`, коли відповідь опрацьовано й факт потрапив у книгу.

### Системна інструкція (додавати до кожного промпту)

```text
Відповідай лише на основі проіндексованої документації. Для кожного твердження дай джерело:
URL сторінки й назву розділу. Вказуй, з якої версії бібліотеки діє поведінка і чи вона застаріла.
Якщо в документації відповіді немає — так і скажи, не вигадуй.
Приклади коду — мінімальні, повні (з імпортами), для Python 3.12, FastAPI ≥ 0.115, Pydantic 2,
SQLAlchemy 2. Для кожного прикладу напиши, який вивід очікувати.
Окремо перелічи: типові помилки, як їх діагностувати, наслідки для безпеки.
Формат: Markdown; терміни англійською в `коді`, пояснення — українською.
```

## Частина I. HTTP і дизайн REST API

- [ ] Опиши структуру HTTP-запиту й відповіді (стартовий рядок, заголовки, тіло) і як FastAPI/Starlette дає доступ до кожної частини (`Request`, `Response`, `Header`, `Cookie`).
- [ ] Семантика методів GET, POST, PUT, PATCH, DELETE: безпечність, ідемпотентність, кешованість за RFC 9110. Як це впливає на дизайн ендпоінтів?
- [ ] Коди відповідей, які має повертати REST API: 200/201/202/204, 400/401/403/404/409/422/429, 500/503. Коли `400`, а коли `422`? Що кажуть RFC 9110 і документація FastAPI?
- [ ] Принципи REST (ресурси, однорідний інтерфейс, відсутність стану, кешування) — що з них реально застосовують у JSON API, а що ні.
- [ ] Іменування ресурсів і вкладених ресурсів, фільтрація, сортування, пагінація (offset/limit проти cursor): переваги й пастки кожного.
- [ ] Версіонування API: у шляху, заголовку, параметрі. Як організувати версії через `APIRouter(prefix=...)` у FastAPI?
- [ ] Формат помилок: RFC 9457 (Problem Details) проти стандартного `detail` у FastAPI. Як підмінити обробник `RequestValidationError` і `HTTPException`?
- [ ] REST, gRPC, GraphQL, WebSocket, SSE, webhook: для яких задач кожен, як кожен підтримує FastAPI або Starlette?
- [ ] CORS: що це, коли браузер робить preflight, як налаштувати `CORSMiddleware` і які налаштування небезпечні (`allow_origins=["*"]` з `allow_credentials`).

## Частина II. Типи й Pydantic

- [ ] Анотації типів у Python 3.10+: `X | None`, `list[str]`, `Literal`, `Annotated`, `TypedDict`, `Protocol`. Що з них використовує FastAPI в рантаймі, а що — лише mypy?
- [ ] Pydantic 2: `BaseModel`, `Field` (обмеження), `model_validate`, `model_dump`, `model_dump(mode="json")`, `exclude_unset`. Різниця з Pydantic 1 для тих, хто мігрує.
- [ ] Режими перевірки: lax і strict. Які перетворення типів Pydantic робить сам (`"5"` → `5`), як їх вимкнути?
- [ ] `field_validator`, `model_validator` (before/after), `computed_field`: коли що, приклади.
- [ ] Типи Pydantic для URL, email, дат: `HttpUrl`, `AnyUrl`, `EmailStr`, `AwareDatetime`. Що повертає `HttpUrl` у Pydantic 2 і як його серіалізувати?
- [ ] `ValidationError`: структура помилки (`type`, `loc`, `msg`, `input`, `ctx`), як її показати користувачу.
- [ ] `pydantic-settings`: налаштування зі змінних середовища й `.env`, `SecretStr`, пріоритет джерел.
- [ ] `ConfigDict`: `extra="forbid"`, `frozen`, `from_attributes` (для об'єктів ORM).

## Частина III. Ядро FastAPI (розділи написано — промпти для перевірки й доповнення)

- [ ] Як FastAPI визначає джерело параметра (шлях, рядок запиту, тіло, заголовок) за підписом функції? Повні правила, включно з `Annotated`.
- [ ] `response_model` проти анотації повернення: пріоритет, фільтрація полів, `response_model_exclude_none`, вплив на продуктивність.
- [ ] `HTTPException` проти власних обробників винятків (`@app.exception_handler`); як не загубити заголовки (`WWW-Authenticate`, `Retry-After`).
- [ ] `Depends`: кешування в межах запиту (`use_cache`), залежності з `yield` і порядок виконання коду після `yield` відносно відповіді (зміни в останніх версіях FastAPI).
- [ ] `lifespan` проти застарілих `on_event("startup")`: як переносити, що зберігати в `app.state`.
- [ ] `APIRouter`: `prefix`, `tags`, `dependencies` на рівні роутера, `include_router` — організація великого застосунку.
- [ ] Генерація OpenAPI: `operation_id`, `openapi_extra`, `callbacks`, `webhooks`, кастомізація `app.openapi()`.
- [ ] FastAPI, Flask, Django (і Django Ninja): що з офіційної сторінки FastAPI «Alternatives, Inspiration and Comparisons» варто процитувати.

## Частина IV. Async і конкурентність

- [ ] Цикл подій asyncio: корутини, задачі, `await`, `gather`, `TaskGroup`, `timeout`. Мінімальні приклади з очікуваним виводом.
- [ ] Як FastAPI/Starlette виконує `def`-ендпоінти в пулі потоків: розмір пулу AnyIO за замовчуванням, як його змінити, що буде при вичерпанні.
- [ ] Що блокує цикл подій: `time.sleep`, `requests`, синхронні драйвери БД, CPU-важкі обчислення. Як виявити (debug-режим asyncio, `slow_callback_duration`)?
- [ ] `run_in_threadpool`, `asyncio.to_thread`, `ProcessPoolExecutor` для CPU-задач — коли що.
- [ ] HTTP-клієнт `httpx.AsyncClient` і `aiohttp`: пул з'єднань, таймаути, ліміти, повторне використання клієнта в `lifespan`.
- [ ] Обмеження конкурентності: `asyncio.Semaphore`, ліміти з'єднань — як не покласти чужий сайт при паралельному збиранні.
- [ ] uvicorn: воркери, `--workers` проти кількох контейнерів, `--reload`, `--proxy-headers`, коректна зупинка.

## Частина V. Бази даних: SQLAlchemy 2 async і Alembic

- [ ] SQLAlchemy 2: `create_async_engine`, `async_sessionmaker`, `AsyncSession`; параметри пулу (`pool_size`, `max_overflow`, `pool_pre_ping`).
- [ ] Декларативні моделі 2.0: `DeclarativeBase`, `Mapped`, `mapped_column`, зв'язки, `UniqueConstraint`, індекси.
- [ ] Запити в стилі 2.0: `select`, `insert ... on_conflict_do_nothing` (PostgreSQL і SQLite), `update`, `delete`, `scalars()`, `RETURNING`.
- [ ] Сесія на запит у FastAPI через залежність з `yield`: коли commit і rollback, чому commit має статися до відповіді.
- [ ] Lazy loading в async-режимі (`MissingGreenlet`): причина й рішення (`selectinload`, `expire_on_commit=False`).
- [ ] Патерни Repository і Unit of Work поверх `AsyncSession`: що кажуть документація SQLAlchemy та FastAPI.
- [ ] Alembic: async `env.py`, `revision --autogenerate`, що autogenerate не бачить, `alembic check`, міграції даних, downgrade.
- [ ] Пошук без урахування регістру й Unicode: `ilike`, `lower()` у SQLite, `pg_trgm` і GIN-індекс у PostgreSQL, `autoescape` у `contains`.
- [ ] SQLModel: що дає і чим відрізняється від окремих Pydantic + SQLAlchemy моделей.

## Частина VI. Middleware, кеш, Redis, фонові задачі

- [ ] Middleware у Starlette: `BaseHTTPMiddleware` проти чистого ASGI-middleware — обмеження, продуктивність, порядок виконання.
- [ ] Middleware для request id і часу обробки; логування з контекстом (`contextvars`).
- [ ] `redis.asyncio`: клієнт, пул з'єднань, `aclose`, транзакції (`pipeline(transaction=True)`), `SET NX EX`, `INCR`, `EXPIRE NX`.
- [ ] Патерн cache-aside: TTL, інвалідація через версію ключа, захист від одночасного перерахунку кешу (thundering herd).
- [ ] Rate limit: фіксоване вікно, ковзне вікно, token bucket; відповідь `429` і заголовок `Retry-After`.
- [ ] `BackgroundTasks` у FastAPI: коли виконується, обмеження (той самий процес, зникає при перезапуску); альтернативи — Celery, arq, RQ.
- [ ] `fakeredis` для тестів: що він підтримує і де поводиться інакше, ніж справжній Redis.

## Частина VII. Тестування API

- [ ] `TestClient` проти `httpx.AsyncClient` з `ASGITransport`: коли кожен, як запустити `lifespan` у тестах.
- [ ] pytest-asyncio: режими `auto`/`strict`, цикл подій на сесію чи функцію, фікстури з `yield`.
- [ ] `app.dependency_overrides`: підміна бази, Redis, клієнта LLM; як прибрати підміни після тесту.
- [ ] Моки: `unittest.mock.patch` («патчити там, де використовують»), `AsyncMock`; коли краще фейк — локальний HTTP-сервер.
- [ ] Фікстури з HTML-сторінками й JSON: організація `tests/fixtures`, `conftest.py` на рівнях.
- [ ] Тести з PostgreSQL у CI: окрема база, транзакція з відкатом на тест проти створення схеми.
- [ ] pytest-cov: покриття гілок, `.coveragerc`, `fail_under`; що покриття НЕ гарантує.
- [ ] Маркери pytest (`-m "not docker"`), параметризація, `xfail` проти `skip`.

## Частина VIII. Безпека

- [ ] OAuth2 password flow у FastAPI: `OAuth2PasswordBearer`, `OAuth2PasswordRequestForm`, кнопка Authorize у `/docs`.
- [ ] JWT: структура, підпис HS256, обов'язкові claims (`exp`, `sub`), атаки на алгоритм (`alg=none`, плутанина ключів), PyJWT ≥ 2.4.
- [ ] Хешування паролів: bcrypt (ліміт 72 байти), argon2; чому FastAPI-документація перейшла з passlib на pwdlib.
- [ ] `401` проти `403`, заголовок `WWW-Authenticate`; залежність `require_admin`.
- [ ] SSRF: перевірка схеми, резолв DNS і перевірка IP (приватні, loopback, link-local, IPv6-mapped), DNS rebinding, редіректи.
- [ ] Підписані webhook: HMAC-SHA256 від часу + тіла, `hmac.compare_digest`, вікно часу проти повторів — як у GitHub і Stripe.
- [ ] Ліміт розміру тіла запиту, таймаути, захист від повільних клієнтів у uvicorn і nginx.
- [ ] Prompt injection для ендпоінтів з LLM: розділення інструкцій і даних, перевірка відповіді схемою.
- [ ] Секрети: `.env`, `SecretStr`, секрети GitHub Actions, що не можна логувати.

## Частина IX. Інтеграції: LLM і Telegram

- [ ] Google Gemini SDK (`google-genai`): async-клієнт, structured output за JSON Schema / Pydantic, ліміти й помилки квоти.
- [ ] Anthropic SDK: async-клієнт, structured outputs, повтори й таймаути, підрахунок токенів і вартості.
- [ ] Спільний інтерфейс для кількох провайдерів LLM (`Protocol`), фейковий клієнт для тестів.
- [ ] Circuit breaker: стани closed/open/half-open, зберігання стану в Redis, поєднання з повторами й backoff.
- [ ] Кешування відповідей LLM: ключ (модель + промпт + версія схеми), TTL, інвалідація.
- [ ] aiogram 3: `Bot`, `Dispatcher`, `Router`, фільтри `Command`, outer/inner middleware, впровадження залежностей у handler.
- [ ] Telegram Bot API: `parse_mode=HTML` (дозволені теги, екранування), ліміт 4096 символів, `429` з `retry_after`, `403` від заблокованого бота.
- [ ] Polling проти webhook: `setWebhook`, `secret_token`, обробка webhook у FastAPI-ендпоінті.
- [ ] Локальний Bot API server і `TelegramAPIServer.from_base` — тестування без справжнього Telegram.
- [ ] AI-інструменти розробника (Claude Code): `CLAUDE.md`, дозволи, hooks, skills — що з документації варто показати на проєкті.

## Частина X. Docker, Compose, CI/CD

- [ ] Dockerfile для FastAPI з офіційної документації FastAPI («FastAPI in Containers»): базовий образ, порядок шарів, `CMD` у формі exec.
- [ ] `.dockerignore`, багатоетапна збірка, користувач без root, `PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED`.
- [ ] `HEALTHCHECK`, `/health` проти `/health/ready`, коректна зупинка (SIGTERM, `--timeout-graceful-shutdown`).
- [ ] Docker Compose: `depends_on` з `condition: service_healthy`, одноразовий сервіс міграцій (`service_completed_successfully`), томи, мережі, `--wait`.
- [ ] nginx перед uvicorn: `proxy_pass`, `X-Forwarded-For`, `--forwarded-allow-ips`, ліміти, TLS (certbot або Caddy).
- [ ] Бекап PostgreSQL з контейнера: `pg_dump`, `set -o pipefail`, відновлення й перевірка бекапу.
- [ ] GitHub Actions: тригери (`pull_request`, `push`), матриця Python, `services: postgres`, кеш pip/uv, `concurrency`, мінімальні `permissions`.
- [ ] Перевірка мінімальних версій залежностей (`uv --resolution lowest-direct`), `mypy --strict` у CI.
- [ ] Публікація образу в ghcr.io: `docker/login-action`, `metadata-action`, теги з SHA, `GITHUB_TOKEN` з `packages: write`.
- [ ] Smoke-тест усього стеку в CI після `docker compose up --wait`.
- [ ] Мікросервіси: коли ділити застосунок, а коли ні (що кажуть документація FastAPI і загальні джерела).

## Довідник і Deep Dive

- [ ] Шпаргалка FastAPI: параметри (`Path`, `Query`, `Body`, `Header`, `Cookie`, `Form`, `File`), відповіді (`JSONResponse`, `StreamingResponse`, `FileResponse`), статус-коди.
- [ ] Файли: `UploadFile`, ліміти розміру, потокове завантаження й віддача.
- [ ] WebSocket і Server-Sent Events у FastAPI: мінімальні приклади, де вони потрібні.
- [ ] Шлях запиту від сокета до функції: uvicorn → ASGI scope → middleware Starlette → маршрутизатор → залежності → ендпоінт → серіалізація.
- [ ] Чекліст перед продакшеном з документації FastAPI (Deployment Concepts): HTTPS, перезапуски, реплікація, пам'ять, кроки перед стартом.
- [ ] Від Django до FastAPI: відповідники `settings.py`, `urls.py`, middleware, сигналів, `request.user`, management-команд.
- [ ] Глосарій: ASGI, WSGI, event loop, DI, ORM, міграція, ідемпотентність, CORS, SSRF, HMAC, JWT, circuit breaker, health check — визначення з першоджерел.
- [ ] Troubleshooting: `422` без очевидної причини, `MissingGreenlet`, `Event loop is closed` у тестах, `address already in use`, `Permission denied` у контейнері, `WinError 10013` на Windows.

## Практика

- [ ] Для кожної частини I–X: 3 вправи зростаючої складності на коді відповідного `steps/NN`, з тестом, який має пройти, і підказкою.
- [ ] Фінальна лаба: пошук за заголовком через `pg_trgm` + GIN-індекс і міграцію Alembic; як перевірити через `EXPLAIN`, що індекс використовується.
