# Крок 8. Безпека: JWT, SSRF, webhook

> **Код кроку:** [`steps/08_security`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/08_security) · відповідає уроку 47 курсу.
>
> **Передумови:** [Крок 7. Аналіз новин через LLM API](../07_llm_api/index.md).

## Що додаємо

Запис дозволено лише адміну з JWT (пароль — bcrypt), RSS-джерела додаються за URL без SSRF (`safe_fetch`), зовнішні системи викликають збір через підписаний HMAC webhook.

## Теми кроку

1. Адмін і JWT
2. SSRF: куди ходить сервер
3. Підписані webhook
4. Тести безпеки

!!! info "Сторінки кроку — у роботі"
    Покроковий розбір цих тем з'явиться тут. Поки що — код кроку, README в його папці й теорія:
    [Частина VIII. Безпека API](../../08_security/README.md).

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
│   └── api.py        ← FastAPI: /api/news (+ CRUD, кеш), /stats, POST /api/scrape, /api/scrape/jobs,
│                       POST /api/news/{id}/analyze, /api/analyze/jobs; урок 47: /api/admin/token, /api/sources,
│                       POST /api/webhooks/scrape; запис — лише з токеном адміна
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── migrations/       ← урок 39: Alembic — версії схеми бази (0001: таблиця news; 0002: колонки аналізу LLM; 0003: таблиця sources)
├── alembic.ini
├── docker-compose.yml ← PostgreSQL 16 (урок 39) і Redis 7 (урок 40) для розробки
├── postman/news_hub.postman_collection.json   ← 18 запитів з перевірками; пароль адміна — змінна adminPassword
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
├── CLAUDE.md         ← урок 43: інструкції для AI-асистента — команди, структура, правила проєкту
├── .claude/          ← урок 43: settings.json (дозволи), hooks/unit_tests.py (pytest -m unit після правок),
│                       skills/add-news-source/ (/add-news-source)
├── pytest.ini        ← урок 42: маркери unit / integration, asyncio
├── .coveragerc       ← урок 42: покриття гілок, concurrency = thread,greenlet (async SQLAlchemy)
└── tests/
    ├── conftest.py   ← фікстура html("…"), маркер за папкою
    ├── factories.py  ← make_raw(**зміни) — тестова новина
    ├── fixtures/     ← збережені сторінки: справжній фрагмент rbc.ua, демо-розмітка, pravda_rss.xml (навчальний знімок RSS)
    ├── unit/         ← парсер, модель, конвеєр, скрапер під моком; test_pravda.py — специфікація для AI,
    │                   test_pravda_review.py — що знайшла рецензія його коду
    ├── integration/  ← API (TestClient і httpx.AsyncClient), CRUD, Redis, справжній get_db,
    │                   скрапер проти локального aiohttp-сервера; test_analyze_api.py — аналіз LLM через API;
    │                   урок 47: test_admin_api.py (хто може писати), test_sources_ssrf.py, test_webhooks_api.py
    └── live/         ← урок 44: справжні виклики моделі — лише pytest -m llm (потрібен ключ і мережа)
```

Джерела коду: `security.py` — `production_bot/backend/core/security.py`, `api/deps.py` і `api/admin/auth.py`; `webhooks.py` — `production_bot/backend/api/webhook.py`; `safe_fetch.py` — розділ A10 (SSRF) конспекту `OWASP_TOP_10.md`; `llm.py` — `ai_bot/app/services/ai_service.py` (пул моделей Gemini, circuit breaker), `analysis.py` замінює `news_dashboard/app/nlp.py`; Redis-клієнт — `production_bot/backend/core/redis.py`, rate limit — `ai_bot/app/middlewares/rate_limit.py` і `repositories/rate_limit_repo.py`, фоновий збір — `/api/scrape/archive` з `news_dashboard`; база й репозиторій — стартовий `production_bot/backend/core/database.py`, `repositories/base.py`, `migrations/`; API і скрапер — прототип `news_dashboard/app/main.py` і `scraper.py`; `parse_rbc_news` — ноутбук про веб-скрапінг `note_lesson_32_web_scraping.ipynb`; словник категорій — `news_dashboard/app/scraper.py`. Знімок — `rbc_news.json` поруч із тим самим ноутбуком.

## Запуск

Усі команди — з папки кроку: `cd steps/08_security`.

```bash
pip install -r requirements.txt
pytest                      # 279 тестів: SQLite у пам'яті + fakeredis + локальні aiohttp-сервери + FakeLLM
pytest -m unit              # лише швидкі, без бази, Redis і мережі
pytest --cov=news_hub       # покриття (налаштування — .coveragerc)
mypy --strict news_hub      # перевірка типів

# база: без DATABASE_URL — файл news_hub.db (SQLite); з PostgreSQL:
docker compose up -d db redis
export DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub   # Windows: set DATABASE_URL=...
export REDIS_URL=redis://localhost:6379/0                                     # без Redis: REDIS_URL=fakeredis://

alembic upgrade head        # створити / оновити таблиці
uvicorn news_hub.api:app --reload
```

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
git diff --no-index --stat steps/07_llm_api steps/08_security
git diff --no-index steps/07_llm_api/news_hub steps/08_security/news_hub
```

## Що далі

[Крок 9. Telegram-бот](../09_telegram_bot/index.md)
