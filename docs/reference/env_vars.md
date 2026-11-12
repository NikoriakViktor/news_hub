# Змінні середовища

Усі змінні фінальної версії (`steps/12_ci_cd`): хто їх читає, що буде без них і з якого кроку вони є. Список
зібрано з коду, не з `README`:

```bash
cd steps/12_ci_cd
grep -rn "os.getenv\|os.environ\|env.get(" --include=*.py news_hub scripts migrations tests
grep -n '\${\?[A-Z_]\+' docker-compose.yml Dockerfile scripts/*.sh .env.example
```

«Крок» — перший крок, у коді якого змінна з'являється (`grep -rlw ІМ'Я steps/*/`). «Коли читається»: **імпорт** —
значення беруться один раз при `import news_hub...` (у тестах змінну треба задати до імпорту); **старт** — у
`lifespan`, при кожному запуску застосунку.

## База й Redis { #db-redis }

| Змінна | За замовчуванням | Хто читає | Коли | Крок |
|---|---|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///news_hub.db` (файл у поточній папці) | `news_hub/db.py`; `migrations/env.py` бере звідти ж | імпорт | 3 |
| `REDIS_URL` | `redis://localhost:6379/0`; `fakeredis://` — Redis у пам'яті процесу | `news_hub/cache.py` | імпорт | 4 |

Значення в різних середовищах:

| Де | `DATABASE_URL` | `REDIS_URL` |
|---|---|---|
| локально | `postgresql+asyncpg://news:news@localhost:5432/news_hub` (крок 3–10) або SQLite за замовчуванням | `redis://localhost:6379/0` |
| образ (`Dockerfile`, крок 10) | `ENV DATABASE_URL=sqlite+aiosqlite:////data/news_hub.db` — на томі `/data` | треба передати |
| Compose (крок 11) | `postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}` | `redis://redis:6379/0` |
| CI, job `postgres` | `postgresql+asyncpg://news:news@localhost:5432/news_hub_test` | — (тести беруть `TEST_REDIS_URL`) |

Усередині контейнера `localhost` — сам контейнер: адреси сервісів — за іменами (`postgres`, `redis`).

## LLM { #llm }

| Змінна | За замовчуванням | Хто читає | Коли | Без неї | Крок |
|---|---|---|---|---|---|
| `LLM_PROVIDER` | `gemini` | `make_llm()` у `news_hub/llm.py` | старт | — | 7 |
| `GEMINI_API_KEY` | — | `make_llm()` | старт | аналіз → `503 LLM не налаштовано` | 7 |
| `GEMINI_MODELS` | `gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash,gemini-2.0-flash-lite` (`MODEL_POOL`) | `make_llm()` | старт | пул за замовчуванням | 7 |
| `ANTHROPIC_API_KEY` | — | `make_llm()`, лише з `LLM_PROVIDER=anthropic` | старт | `503` | 7 |
| `ANTHROPIC_MODEL` | — | `make_llm()`, разом з ключем | старт | `503` | 7 |
| `LLM_TIMEOUT` | `30` (секунд на запит) | `news_hub/llm.py` | імпорт | — | 7 |
| `LLM_MAX_TOKENS` | `2048` | `news_hub/llm.py` | імпорт | — | 7 |

`LLM_PROVIDER`: `gemini`, `anthropic` або `fake` (`FakeLLM`, без мережі — для розробки); інше значення —
`ValueError` і `Application startup failed`. Детально — [крок 7](../tutorials/07_llm_api/llm_client.md).

## Ліміти запитів { #rate-limit }

| Змінна | За замовчуванням | Що обмежує | Крок |
|---|---|---|---|
| `RATE_LIMIT_REQUESTS` | `5` | `POST /api/scrape*` за вікно | 4 |
| `RATE_LIMIT_WINDOW` | `60` (с) | вікно для збору й аналізу | 4 |
| `ANALYZE_RATE_LIMIT` | `10` | `POST …/analyze`, `POST /api/analyze/*` за `RATE_LIMIT_WINDOW` | 7 |
| `LOGIN_RATE_LIMIT` | `5` | `POST /api/admin/token` за вікно (рахує й вдалі спроби) | 8 |
| `LOGIN_RATE_WINDOW` | `300` (с) | вікно для входу | 8 |
| `LOGIN_FAIL_LIMIT` | `20` | **невдалих** входів під одним іменем з усіх адрес разом; після межі `POST /api/admin/token` → `429` «забагато невдалих входів під цим іменем; спробуй через N с», навіть на правильний пароль; вдалий вхід скидає лічильник | 8 |
| `LOGIN_FAIL_WINDOW` | `900` (с) | вікно лічильника за ім'ям (ключ Redis `login:fail:<хеш імені>`) | 8 |

Перші п'ять читає `news_hub/middleware.py` при імпорті (таблиця `LIMITS`; `/scrape` у бота бере звідти ж межу
збору, лічильник `rate:scrape:tg<id>`), `LOGIN_FAIL_*` — `news_hub/security.py` (`LoginGuard`). Перевищення —
`429` з `Retry-After` ([Rate limit](../tutorials/04_middleware_redis/rate_limit.md),
[ліміт входу за ім'ям](../08_security/secrets_and_headers.md#news-hub-fixes)).

## Адмін і webhook { #security }

| Змінна | За замовчуванням | Хто читає | Без неї / неправильна | Крок |
|---|---|---|---|---|
| `JWT_SECRET` | — | `load_admin_settings()` у `news_hub/security.py`, старт | разом з `ADMIN_PASSWORD_HASH` порожні — запис → `503`; коротша за 32 символи — `RuntimeError` при старті | 8 |
| `ADMIN_PASSWORD_HASH` | — | `load_admin_settings()`, старт | не bcrypt-хеш (`$2b$12$` + 53 символи) — `RuntimeError` | 8 |
| `ADMIN_USERNAME` | `admin` | `load_admin_settings()`, старт | — | 8 |
| `JWT_EXPIRE_MINUTES` | `30` | `load_admin_settings()`, старт | — | 8 |
| `BOT_ADMIN_IDS` | порожньо | `load_admin_settings()` → `AdminSettings.telegram_ids`; бот бере його через `telegram_admin_ids()` | id користувачів Telegram через кому, кому можна `/scrape`; без `JWT_SECRET` і `ADMIN_PASSWORD_HASH` — `RuntimeError` «BOT_ADMIN_IDS задано, а адмін-доступ — ні: задай JWT_SECRET і ADMIN_PASSWORD_HASH (адмін один для API і бота)»; не число — `RuntimeError` «BOT_ADMIN_IDS — числові id Telegram через кому, наприклад 1001,2002» | 9 |
| `WEBHOOK_SECRET` | — | `load_webhook_secret()` у `news_hub/webhooks.py`, старт | порожня — `POST /api/webhooks/scrape` → `503`; коротша за 32 — `RuntimeError` | 8 |
| `DOCS_ENABLED` | `true`; у Compose (кроки 11–12) — `${DOCS_ENABLED:-false}` | `docs_enabled()` у `news_hub/api.py`, при імпорті | `0`, `false`, `no`, `off` (без різниці регістру й пробілів) — `/docs`, `/redoc` і `/openapi.json` → `404` | 8 |

Значення дає `python -m news_hub.security` (з `--env-file` — без лапок, для `docker run --env-file`). У хеші є `$`:
у shell і `.env` для Compose — **одинарні** лапки ([Секрети в `.env`](../tutorials/11_compose_deploy/env_secrets.md)).

## Telegram { #telegram }

| Змінна | За замовчуванням | Хто читає | Без неї / неправильна | Крок |
|---|---|---|---|---|
| `BOT_TOKEN` | — | `load_bot_settings()` у `news_hub/bot/settings.py`: `lifespan` API і `python -m news_hub.bot` | бота немає, API працює; `python -m news_hub.bot` завершується з кодом 1 | 9 |
| `TELEGRAM_WEBHOOK_URL` | — | `load_bot_settings()` | порожня — режим polling (`python -m news_hub.bot`); не `https://` без `TELEGRAM_API_URL` — `RuntimeError` | 9 |
| `TELEGRAM_WEBHOOK_SECRET` | — | `load_bot_settings()` | з `TELEGRAM_WEBHOOK_URL` обов'язкова: 32–256 символів `A-Z a-z 0-9 _ -`, інакше `RuntimeError` | 9 |
| `TELEGRAM_API_URL` | — (справжній `api.telegram.org`) | `load_bot_settings()` → `create_bot` | — ; для двійника: `http://127.0.0.1:8081`, у Compose `http://twin:8081` | 9 |

Докладно — [Polling і webhook](../tutorials/09_telegram_bot/polling_webhook.md). `BOT_ADMIN_IDS` — не тут, а в [адмінських змінних](#security): адмін один для API і бота.

## Compose, uvicorn, скрипти { #infra }

| Змінна | За замовчуванням | Хто читає | Крок |
|---|---|---|---|
| `POSTGRES_DB` | `news_hub` | `docker-compose.yml`: сервіс `postgres` і `DATABASE_URL` для `api`, `migrate`, `bot`; `scripts/backup.sh`, `restore.sh` (усередині контейнера) | 3 (сталі в `docker-compose.yml`), 11 (з `.env`) |
| `POSTGRES_USER` | `news` | те саме | 3, 11 |
| `POSTGRES_PASSWORD` | обов'язкова: `${POSTGRES_PASSWORD:?задай POSTGRES_PASSWORD у .env}` | те саме | 3, 11 |
| `HTTP_PORT` | `80` | `docker-compose.yml` (порт nginx), `scripts/smoke.sh`, `scripts/make_env.py` | 11 |
| `FORWARDED_ALLOW_IPS` | в uvicorn — `127.0.0.1,::1`; у Compose — `172.28.0.10` (адреса nginx) | uvicorn: кому вірити в `X-Forwarded-For` | 11 |
| `WEB_CONCURRENCY` | не задано → 1 процес | uvicorn: кількість воркерів, якщо немає `--workers` | 10 |
| `ADMIN_PASSWORD` | `make_env.py` — випадковий; `smoke.sh` — обов'язкова | `scripts/make_env.py` (хеш у `.env`), `scripts/smoke.sh` (вхід) | 12 |
| `COMPOSE_PROJECT_NAME` | ім'я з `name: news_hub` | Docker Compose; потрібна скриптам, якщо стек запущено з `-p <ім'я>` | 11 |

Пароль бази стає частиною URL: без символів `@ : / ? #` (`.env.example`).

## Образ { #image }

`Dockerfile` задає сам (крок 10): `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`,
`PIP_DISABLE_PIP_VERSION_CHECK=1`, `PIP_ROOT_USER_ACTION=ignore`, `DATABASE_URL=sqlite+aiosqlite:////data/news_hub.db`.
Пояснення — [Користувач, дані й змінні середовища](../tutorials/10_docker/user_data_env.md).

## Тести { #tests }

| Змінна | За замовчуванням | Хто читає | Крок |
|---|---|---|---|
| `TEST_DATABASE_URL` | `sqlite+aiosqlite://` (у пам'яті) | `tests/integration/conftest.py` | 3 |
| `TEST_REDIS_URL` | `fakeredis://` | `tests/integration/conftest.py` → `REDIS_URL` до імпорту `news_hub` | 4 |

`tests/integration/conftest.py` сам задає тестові `JWT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`
(bcrypt з 4 раундами) і `WEBHOOK_SECRET` — не з `.env`. У CI (job `postgres`):
`TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test`, `TEST_REDIS_URL=redis://localhost:6379/15`.
`tests/live/test_llm_live.py` (`pytest -m llm`) читає `LLM_PROVIDER` і ключ провайдера.

## `.env` { #dotenv }

[`steps/12_ci_cd/.env.example`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/.env.example)
перелічує те, що задають на сервері: `POSTGRES_*`, `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `JWT_SECRET`,
`LOGIN_FAIL_LIMIT`, `LOGIN_FAIL_WINDOW`, `WEBHOOK_SECRET`, `LLM_PROVIDER`, `GEMINI_API_KEY`, `BOT_*`, `TELEGRAM_*`,
`HTTP_PORT`, `DOCS_ENABLED=false`. Compose читає `.env` двічі:
для `${…}` у `docker-compose.yml` і як `env_file` для `api`, `migrate`, `bot`. Створити з випадковими секретами —
`python scripts/make_env.py` ([Команди](commands.md#scripts)). Сам застосунок `.env` не читає: локально змінні
задають через `export`.
