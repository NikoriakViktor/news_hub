# Крок 11. Docker Compose і деплой

> **Код кроку:** [`steps/11_compose_deploy`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/11_compose_deploy) · відповідає уроку 50 курсу.
>
> **Передумови:** [Крок 10. Docker-образ](../10_docker/index.md).

## Що додаємо

Уся система одним Compose-файлом: nginx → api → PostgreSQL + Redis, міграції окремим кроком, бот, справжній IP клієнта за nginx, секрети в `.env`, бекап і відновлення, деплой на сервер.

## Теми кроку

1. Порядок запуску: healthy, а не «запущено»
2. nginx і справжній IP клієнта
3. Секрети в `.env`
4. Зовнішній сервіс не зупиняє старт
5. Деплой на сервер

!!! info "Сторінки кроку — у роботі"
    Покроковий розбір цих тем з'явиться тут. Поки що — код кроку, README в його папці й теорія:
    [Частина X. Docker, Compose і CI/CD](../../10_docker_and_ci/README.md).

## Структура після кроку

```
news_hub/
├── news_hub/
│   ├── parser.py     ← стартовий parse_rbc_news + типи: HTML → list[RawNews]
│   ├── rss.py        ← урок 43: parse_pravda_rss — RSS «Української правди» → list[RawNews] (написав Claude Code)
│   ├── models.py     ← NewsItem (Pydantic), validate_news, is_allowed_host (rbc.ua, pravda.com.ua, epravda.com.ua)
│   ├── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
│   ├── scraper.py    ← урок 38: сторінки rbc.ua через aiohttp — разом (gather) або по черзі
│   ├── db.py         ← урок 39: engine, сесії, get_db (сесія й транзакція на запит)
│   ├── tables.py     ← урок 39: NewsRow — таблиця news (SQLAlchemy 2.0)
│   ├── repository.py ← урок 39: NewsRepository — увесь SQL; замінив NewsStore з уроку 38
│   ├── cache.py      ← урок 40: клієнт Redis, NewsCache (cache-aside з версією)
│   ├── middleware.py ← урок 40: X-Request-ID / X-Process-Time, rate limit → 429, інвалідація кешу
│   ├── jobs.py       ← урок 40: фоновий збір, статус задачі в Redis; урок 44: пакетний аналіз LLM
│   ├── llm.py        ← урок 44: LLMClient — GeminiClient (пул моделей), AnthropicClient, FakeLLM; CircuitBreaker у Redis
│   ├── analysis.py   ← урок 44: NewsAnalysis (Pydantic), промпт, analyze_news (перевірка + 1 повтор), кеш за хешем тексту
│   ├── security.py   ← урок 47: пароль адміна (bcrypt), JWT, require_admin (401 / 403 / 503)
│   ├── safe_fetch.py ← урок 47: завантаження чужого URL без SSRF — схема, порт, IP після DNS, кожне перенаправлення
│   ├── webhooks.py   ← урок 47: підпис HMAC (час + тіло), вікно 5 хв, захист від повтору
│   ├── bot/          ← урок 48: aiogram — factory.py (Bot, Dispatcher), handlers.py (команди), middlewares.py
│   │                   (rate limit, сесія бази на update), formatting.py (HTML, 4096), settings.py; __main__ — polling
│   ├── notify.py     ← урок 48: нові новини → підписникам (403 — видалити підписки, 429 — retry_after)
│   └── api.py        ← FastAPI: /api/news (+ CRUD, кеш), /stats, POST /api/scrape, /api/scrape/jobs,
│                       POST /api/news/{id}/analyze, /api/analyze/jobs; урок 47: /api/admin/token, /api/sources,
│                       POST /api/webhooks/scrape; запис — лише з токеном адміна; урок 48: POST /api/telegram/webhook
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── migrations/       ← урок 39: Alembic — версії схеми бази (0001: таблиця news; 0002: колонки аналізу LLM; 0003: таблиця sources; 0004: таблиця subscriptions)
├── alembic.ini
├── Dockerfile        ← урок 49: образ застосунку (основа — production_bot): залежності окремим шаром, користувач app,
│                       SQLite на томі /data, HEALTHCHECK без curl, CMD у exec-формі
├── .dockerignore     ← урок 49: що не потрапляє в образ — .env, .venv, tests, *.db, кеші
├── requirements.txt  ← урок 49: лише залежності роботи (вони йдуть в образ)
├── requirements-dev.txt ← урок 49: + pytest, mypy, fakeredis — для розробки й тестів
├── docker-compose.yml ← урок 50: уся система — postgres, redis, migrate, api, nginx; профілі polling (бот) і twin
├── docker-compose.dev.yml ← урок 50: розробка — порти бази й Redis лише на 127.0.0.1
├── nginx/nginx.conf  ← урок 50: проксі до api, X-Forwarded-For перезаписується (реальний IP для rate limit)
├── scripts/          ← урок 50: backup.sh / restore.sh — pg_dump з контейнера, set -euo pipefail
├── .env.example      ← урок 50: усі змінні стеку; значення з `$` — в одинарних лапках
├── postman/news_hub.postman_collection.json   ← 18 запитів з перевірками; пароль адміна — змінна adminPassword
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
├── CLAUDE.md         ← урок 43: інструкції для AI-асистента — команди, структура, правила проєкту
├── .claude/          ← урок 43: settings.json (дозволи), hooks/unit_tests.py (pytest -m unit після правок),
│                       skills/add-news-source/ (/add-news-source)
├── pytest.ini        ← урок 42: маркери unit / integration, asyncio; урок 49: docker (лише pytest -m docker)
├── .coveragerc       ← урок 42: покриття гілок, concurrency = thread,greenlet (async SQLAlchemy)
└── tests/
    ├── conftest.py   ← фікстура html("…"), маркер за папкою
    ├── factories.py  ← make_raw(**зміни) — тестова новина
    ├── fixtures/     ← збережені сторінки: справжній фрагмент rbc.ua, демо-розмітка, pravda_rss.xml (навчальний знімок RSS)
    ├── unit/         ← парсер, модель, конвеєр, скрапер під моком; test_pravda.py — специфікація для AI,
    │                   test_pravda_review.py — що знайшла рецензія його коду
    ├── integration/  ← API (TestClient і httpx.AsyncClient), CRUD, Redis, справжній get_db,
    │                   скрапер проти локального aiohttp-сервера; test_analyze_api.py — аналіз LLM через API;
    │                   урок 47: test_admin_api.py (хто може писати), test_sources_ssrf.py, test_webhooks_api.py;
    │                   урок 48: test_bot.py (команди), test_notify.py, test_telegram_webhook.py
    ├── docker/       ← урок 49: test_image.py — збірка образу, що в ньому немає, користувач, healthcheck, docker stop
    ├── telegram_twin.py ← урок 48: двійник Telegram Bot API (aiohttp): записує виклики, правила HTML, 403 / 429
    └── live/         ← урок 44: справжні виклики моделі — лише pytest -m llm (потрібен ключ і мережа)
```

Джерела коду: `bot/` — стартовий `ai_bot/app/` (`bot.py`, `handlers/commands.py`, `middlewares/`, `utils/`) і `echo_bot/`; `notify.py` — `production_bot/backend/workers/notifications.py`; webhook — `production_bot/backend/api/webhook.py` і `app.py`; `security.py` — `production_bot/backend/core/security.py`, `api/deps.py` і `api/admin/auth.py`; `webhooks.py` — `production_bot/backend/api/webhook.py`; `safe_fetch.py` — розділ A10 (SSRF) конспекту `OWASP_TOP_10.md`; `llm.py` — `ai_bot/app/services/ai_service.py` (пул моделей Gemini, circuit breaker), `analysis.py` замінює `news_dashboard/app/nlp.py`; Redis-клієнт — `production_bot/backend/core/redis.py`, rate limit — `ai_bot/app/middlewares/rate_limit.py` і `repositories/rate_limit_repo.py`, фоновий збір — `/api/scrape/archive` з `news_dashboard`; база й репозиторій — стартовий `production_bot/backend/core/database.py`, `repositories/base.py`, `migrations/`; API і скрапер — прототип `news_dashboard/app/main.py` і `scraper.py`; `parse_rbc_news` — ноутбук про веб-скрапінг `note_lesson_32_web_scraping.ipynb`; словник категорій — `news_dashboard/app/scraper.py`. Знімок — `rbc_news.json` поруч із тим самим ноутбуком.

## Запуск

Усі команди — з папки кроку: `cd steps/11_compose_deploy`.

```bash
pip install -r requirements-dev.txt   # застосунок + pytest, mypy, fakeredis
pytest                      # 343 тести: SQLite у пам'яті + fakeredis + локальні aiohttp-сервери + двійник Telegram + FakeLLM
pytest -m unit              # лише швидкі, без бази, Redis і мережі
pytest --cov=news_hub       # покриття (налаштування — .coveragerc)
mypy --strict news_hub      # перевірка типів
pytest -m docker            # урок 49: 6 тестів образу (потрібен Docker)

# база: без DATABASE_URL — файл news_hub.db (SQLite); з PostgreSQL і Redis з Compose (cp .env.example .env спершу):
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis
export DATABASE_URL=postgresql+asyncpg://news:<POSTGRES_PASSWORD>@localhost:5432/news_hub   # Windows: set DATABASE_URL=...
export REDIS_URL=redis://localhost:6379/0                                                   # без Redis: REDIS_URL=fakeredis://

alembic upgrade head        # створити / оновити таблиці
uvicorn news_hub.api:app --reload
```

### Уся система в Compose (урок 50)

```bash
cp .env.example .env                  # заповнити: POSTGRES_PASSWORD, рядки з python -m news_hub.security
docker compose up -d --build --wait   # postgres → migrate → api (healthy) → nginx
curl localhost/health/ready           # {"status":"ok","checks":{"database":"ok","redis":"ok"}}
docker compose logs -f api            # журнал
docker compose up -d --build --wait   # оновлення після git pull: перезбирається й перезапускається лише змінене
./scripts/backup.sh                   # backups/news_hub-….sql.gz
./scripts/restore.sh backups/news_hub-….sql.gz
docker compose down                   # зупинити (дані — у томі pgdata; down -v видалить і їх)
```

- api назовні не відкритий — лише через nginx. IP клієнта (rate limit входу, урок 47) — з `X-Forwarded-For`, який nginx
  перезаписує, а uvicorn приймає лише від nginx (`FORWARDED_ALLOW_IPS=172.28.0.10`).
- Міграції — окремий сервіс `migrate` (один раз, до api), а не при старті кожного api.
- Бот у режимі polling: `docker compose --profile polling up -d`. З `TELEGRAM_WEBHOOK_URL` — усередині api;
  реєстрація в Telegram — у фоні з повторами, недоступний Telegram не зупиняє API.
- Двійник Telegram для заняття: `docker compose --profile twin up -d`, у `.env` — `BOT_TOKEN=123456:TEST-TOKEN`,
  `TELEGRAM_API_URL=http://twin:8081`, `TELEGRAM_WEBHOOK_URL=http://nginx/api/telegram/webhook` і секрет.

### Docker (урок 49)

```bash
docker build -t news_hub:48 .
docker network create news
docker run -d --name redis --network news redis:7-alpine
docker run --rm -v news_data:/data news_hub:48 alembic upgrade head        # схема бази на томі
docker run -d --name api --network news -p 8000:8000 -v news_data:/data \
    -e REDIS_URL=redis://redis:6379/0 --env-file .env news_hub:48
curl localhost:8000/health/ready        # {"status":"ok","checks":{"database":"ok","redis":"ok"}}
docker stop api                         # SIGTERM → uvicorn завершується сам, за 1–2 с
```

- `REDIS_URL=redis://localhost:…` у контейнері — це сам контейнер, а не твій комп'ютер: інші контейнери — за
  іменем у спільній мережі (`redis`).
- `--env-file` бере значення **буквально**, разом з лапками: рядки для нього — `python -m news_hub.security --env-file`.
- Без `DATABASE_URL` база — SQLite на томі `/data`; PostgreSQL — `-e DATABASE_URL=postgresql+asyncpg://…`.
- `/health` — «процес живий» (HEALTHCHECK образу), `/health/ready` — база й Redis відповідають (інакше 503).
- Кілька процесів uvicorn — `-e WEB_CONCURRENCY=2`; зазвичай краще більше контейнерів (урок 50).

### Telegram-бот (урок 48)

Без `BOT_TOKEN` бота немає — API працює як раніше. Токен дає @BotFather у Telegram (`/newbot`); це секрет,
лише в змінних середовища.

```bash
# розробка: polling — бот сам питає Telegram про нові повідомлення
BOT_TOKEN=… python -m news_hub.bot

# сервер: webhook — Telegram надсилає update на POST /api/telegram/webhook (лише https)
export BOT_TOKEN=… TELEGRAM_WEBHOOK_URL=https://news.example/api/telegram/webhook
export TELEGRAM_WEBHOOK_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
uvicorn news_hub.api:app          # при старті — setWebhook із секретом; при зупинці webhook лишається
```

Без мережі й токена — двійник Telegram Bot API (`tests/telegram_twin.py`):

```bash
python -m tests.telegram_twin --port 8081                  # «Telegram» на 127.0.0.1:8081
BOT_TOKEN=123456:TEST-TOKEN TELEGRAM_API_URL=http://127.0.0.1:8081 python -m news_hub.bot
curl -X POST localhost:8081/_twin/say -d '{"text": "/news", "chat_id": 1001}'   # «користувач» пише боту
curl localhost:8081/_twin/sent?chat_id=1001                                     # що відповів бот
```

| Змінна | За замовчуванням | Що робить |
|---|---|---|
| `BOT_TOKEN` | — | токен бота; без нього бот вимкнений |
| `TELEGRAM_WEBHOOK_URL` / `TELEGRAM_WEBHOOK_SECRET` | — | webhook у FastAPI; секрет — 32–256 символів `A-Z a-z 0-9 _ -` |
| `TELEGRAM_API_URL` | api.telegram.org | інший сервер Bot API (двійник, локальний Bot API server) |
| `BOT_ADMIN_IDS` | — | `user_id` через кому: кому дозволено `/scrape` у боті |

Команди: `/news [N]`, `/digest`, `/subscribe <слово>`, `/unsubscribe <слово>`, `/subscriptions`, `/help`;
адміну — `/scrape [snapshot]`. Після кожного збору (API, фонова задача, RSS-джерело) нові новини, у заголовку
яких є слово підписки, приходять у чат.

### Адмін, RSS-джерела і webhook (урок 47)

Читати новини може будь-хто; змінювати, збирати, аналізувати й додавати джерела — лише адмін з токеном.
Без `JWT_SECRET` і `ADMIN_PASSWORD_HASH` ці ендпоінти відповідають `503`, а занадто короткий секрет не дасть
застосунку стартувати. У середовищі — **хеш** пароля, не пароль:

```bash
python -m news_hub.security          # спитає пароль → рядки ADMIN_PASSWORD_HASH='$2b$12$…' і JWT_SECRET='…'
export ADMIN_PASSWORD_HASH='$2b$12$…' JWT_SECRET='…'      # одинарні лапки: у хеші є $
export WEBHOOK_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"   # якщо потрібен webhook
uvicorn news_hub.api:app --reload

TOKEN=$(curl -s -X POST localhost:8000/api/admin/token -H 'Content-Type: application/json' \
        -d '{"username": "admin", "password": "…"}' | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -X POST localhost:8000/api/scrape -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"source": "snapshot"}'
```

У Swagger — кнопка **Authorize** (вставити `access_token`). RSS-джерело: `POST /api/sources`
з `{"url": "https://www.pravda.com.ua/rss/view_news/", "name": "Українська правда"}`, потім
`POST /api/sources/1/fetch`. Адреси всередині мережі (localhost, 10.x, 192.168.x, 169.254.169.254, …) — `400`.

| Змінна | За замовчуванням | Що робить |
|---|---|---|
| `JWT_SECRET` | — | ключ підпису токенів, ≥ 32 символи |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` | `admin` / — | вхід адміна; хеш — `python -m news_hub.security` |
| `JWT_EXPIRE_MINUTES` | `30` | скільки живе токен |
| `LOGIN_RATE_LIMIT` / `LOGIN_RATE_WINDOW` | `5` / `300` | спроб входу з однієї адреси за вікно, с |
| `WEBHOOK_SECRET` | — | спільний секрет для підпису `POST /api/webhooks/scrape`; без нього — `503` |

Webhook підписує відправник: `X-Webhook-Timestamp: <unix-час>` і
`X-Webhook-Signature: sha256=<HMAC-SHA256(WEBHOOK_SECRET, "<час>." + тіло)>` (функція `news_hub.webhooks.sign`).

### Аналіз LLM (урок 44)

Ключ — лише змінна середовища, ніколи не в коді й не в git. Без ключа все, крім аналізу, працює;
`POST /api/news/{id}/analyze` відповідає `503 LLM не налаштовано`.

```bash
export GEMINI_API_KEY=…          # безкоштовний ключ: aistudio.google.com → Get API key
uvicorn news_hub.api:app --reload
# або без ключа й мережі — фейкова модель: LLM_PROVIDER=fake uvicorn news_hub.api:app --reload
# Anthropic замість Gemini: LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=… ANTHROPIC_MODEL=<назва моделі>

pytest -m llm                    # справжні виклики (витрачають квоту); без ключа — пропускаються
```

| Змінна | За замовчуванням | Що робить |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini`, `anthropic` або `fake` |
| `GEMINI_MODELS` | `gemini-2.5-flash,…` | пул моделей через кому — перша, що відповіла |
| `LLM_TIMEOUT` / `LLM_MAX_TOKENS` | `30` / `2048` | секунд на запит / стеля відповіді |
| `ANALYZE_RATE_LIMIT` | `10` | запитів до LLM за хвилину з однієї адреси |

Swagger (спершу Authorize — урок 47): `POST /api/scrape` (`{"source": "snapshot"}`) → `POST /api/news/1/analyze` → `POST /api/analyze/jobs`
(`{"limit": 20}`) → `GET /api/news/stats` (поля `ai_category`, `sentiment`) → `GET /api/news?sentiment=негативна`.

Ті самі тести на справжніх серверах: `TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test TEST_REDIS_URL=redis://localhost:6379/15 pytest` (базу `news_hub_test` створи заздалегідь; Redis-база 15 очищується перед кожним тестом). Лише так ловиться гонка в rate limit: fakeredis не віддає керування циклу подій, тож одночасних запитів на ньому не буває (`tests/integration/test_async_api.py`).

- http://127.0.0.1:8000/docs — Swagger UI: Authorize, потім `POST /api/scrape` з `{"source": "snapshot"}`, потім `GET /api/news`;
- Postman: Import → `postman/news_hub.postman_collection.json` → змінна `adminPassword` → Run collection;
- без Postman: `npx newman run postman/news_hub.postman_collection.json --env-var adminPassword=…`.

Свіжа стрічка (коли `www.rbc.ua` доступний з мережі) — `POST /api/scrape` з `{}` або
`{"mode": "sequential"}`; у відповіді — час кожної сторінки й помилки, якщо сторінка не завантажилась.

Урок 43: `rss.py` і зміни в `models.py` написав Claude Code (`claude -p`) за специфікацією `tests/unit/test_pravda.py`.
Рецензія його коду — `tests/unit/test_pravda_review.py`.

## Порівняння з попереднім кроком

```bash
git diff --no-index --stat steps/10_docker steps/11_compose_deploy
git diff --no-index steps/10_docker/news_hub steps/11_compose_deploy/news_hub
```

## Що далі

[Крок 12. CI/CD на GitHub Actions](../12_ci_cd/index.md)
