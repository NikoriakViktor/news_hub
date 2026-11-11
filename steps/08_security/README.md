# news_hub — новинний агрегатор (крок 8: безпека — адмін, SSRF, webhook)

Наскрізний проєкт книги: парсер новин → перевірені моделі → API → база → кеш → підсумки від Gemini → Telegram-бот → Docker. Кожен крок — рефакторинг проєкту попереднього.

| Крок | Що додається |
|---|---|
| 1 | стартовий парсер з анотаціями типів; `NewsItem` на Pydantic |
| 2 | FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman |
| 3 | SQLAlchemy: новини в базі, унікальний `url`, повний CRUD, Alembic |
| 4 | middleware, кеш і rate limit на Redis, фоновий збір |
| 5 | тести: unit / integration, HTML-фікстури, мок і фейк мережі, httpx, покриття |
| 6 | Claude Code у проєкті: CLAUDE.md, дозволи, hook; друге джерело — RSS «Української правди», написане AI за тестами |
| 7 | LLM: підсумок, тема, тональність, ключові слова — Gemini (або Anthropic) за спільним інтерфейсом, перевірка Pydantic, кеш, circuit breaker |
| **8** | **безпека: запис лише адміну з JWT, RSS-джерела за URL без SSRF, підписані webhook** ← ти тут |
| 9 | Telegram-бот: `/news`, `/digest` |
| 48–50 | Docker, Compose, CI/CD |

## Що тут

```
news_hub/
├── news_hub/
│   ├── parser.py     ← стартовий parse_rbc_news + типи: HTML → list[RawNews]
│   ├── rss.py        ← крок 6: parse_pravda_rss — RSS «Української правди» → list[RawNews] (написав Claude Code)
│   ├── models.py     ← NewsItem (Pydantic), validate_news, is_allowed_host (rbc.ua, pravda.com.ua, epravda.com.ua)
│   ├── snapshot.py   ← знімок стрічки: data/rbc_news_snapshot.json → list[RawNews]
│   ├── scraper.py    ← крок 2: сторінки rbc.ua через aiohttp — разом (gather) або по черзі
│   ├── db.py         ← крок 3: engine, сесії, get_db (сесія й транзакція на запит)
│   ├── tables.py     ← крок 3: NewsRow — таблиця news (SQLAlchemy 2.0)
│   ├── repository.py ← крок 3: NewsRepository — увесь SQL; замінив NewsStore з кроку 2
│   ├── cache.py      ← крок 4: клієнт Redis, NewsCache (cache-aside з версією)
│   ├── middleware.py ← крок 4: X-Request-ID / X-Process-Time, rate limit → 429, інвалідація кешу
│   ├── jobs.py       ← крок 4: фоновий збір, статус задачі в Redis; крок 7: пакетний аналіз LLM
│   ├── llm.py        ← крок 7: LLMClient — GeminiClient (пул моделей), AnthropicClient, FakeLLM; CircuitBreaker у Redis
│   ├── analysis.py   ← крок 7: NewsAnalysis (Pydantic), промпт, analyze_news (перевірка + 1 повтор), кеш за хешем тексту
│   ├── security.py   ← крок 8: пароль адміна (bcrypt), JWT, require_admin (401 / 403 / 503)
│   ├── safe_fetch.py ← крок 8: завантаження чужого URL без SSRF — схема, порт, IP після DNS, кожне перенаправлення
│   ├── webhooks.py   ← крок 8: підпис HMAC (час + тіло), вікно 5 хв, захист від повтору
│   └── api.py        ← FastAPI: /api/news (+ CRUD, кеш), /stats, POST /api/scrape, /api/scrape/jobs,
│                       POST /api/news/{id}/analyze, /api/analyze/jobs; крок 8: /api/admin/token, /api/sources,
│                       POST /api/webhooks/scrape; запис — лише з токеном адміна
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── migrations/       ← крок 3: Alembic — версії схеми бази (0001: таблиця news; 0002: колонки аналізу LLM; 0003: таблиця sources)
├── alembic.ini
├── docker-compose.yml ← PostgreSQL 16 (крок 3) і Redis 7 (крок 4) для розробки
├── postman/news_hub.postman_collection.json   ← 18 запитів з перевірками; пароль адміна — змінна adminPassword
├── examples/         ← before_dict.py / after_typed.py — що бачить mypy
├── CLAUDE.md         ← крок 6: інструкції для AI-асистента — команди, структура, правила проєкту
├── .claude/          ← крок 6: settings.json (дозволи), hooks/unit_tests.py (pytest -m unit після правок),
│                       skills/add-news-source/ (/add-news-source)
├── pytest.ini        ← крок 5: маркери unit / integration, asyncio
├── .coveragerc       ← крок 5: покриття гілок, concurrency = thread,greenlet (async SQLAlchemy)
└── tests/
    ├── conftest.py   ← фікстура html("…"), маркер за папкою
    ├── factories.py  ← make_raw(**зміни) — тестова новина
    ├── fixtures/     ← збережені сторінки: справжній фрагмент rbc.ua, демо-розмітка, pravda_rss.xml (навчальний знімок RSS)
    ├── unit/         ← парсер, модель, конвеєр, скрапер під моком; test_pravda.py — специфікація для AI,
    │                   test_pravda_review.py — що знайшла рецензія його коду
    ├── integration/  ← API (TestClient і httpx.AsyncClient), CRUD, Redis, справжній get_db,
    │                   скрапер проти локального aiohttp-сервера; test_analyze_api.py — аналіз LLM через API;
    │                   крок 8: test_admin_api.py (хто може писати), test_sources_ssrf.py, test_webhooks_api.py
    └── live/         ← крок 7: справжні виклики моделі — лише pytest -m llm (потрібен ключ і мережа)
```

## Запуск

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

### Адмін, RSS-джерела і webhook (крок 8)

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

### Аналіз LLM (крок 7)

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

Swagger (спершу Authorize — крок 8): `POST /api/scrape` (`{"source": "snapshot"}`) → `POST /api/news/1/analyze` → `POST /api/analyze/jobs`
(`{"limit": 20}`) → `GET /api/news/stats` (поля `ai_category`, `sentiment`) → `GET /api/news?sentiment=негативна`.

Ті самі тести на справжніх серверах: `TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test TEST_REDIS_URL=redis://localhost:6379/15 pytest` (базу `news_hub_test` створи заздалегідь; Redis-база 15 очищується перед кожним тестом). Лише так ловиться гонка в rate limit: fakeredis не віддає керування циклу подій, тож одночасних запитів на ньому не буває (`tests/integration/test_async_api.py`).

- http://127.0.0.1:8000/docs — Swagger UI: Authorize, потім `POST /api/scrape` з `{"source": "snapshot"}`, потім `GET /api/news`;
- Postman: Import → `postman/news_hub.postman_collection.json` → змінна `adminPassword` → Run collection;
- без Postman: `npx newman run postman/news_hub.postman_collection.json --env-var adminPassword=…`.

Свіжа стрічка (коли `www.rbc.ua` доступний з мережі) — `POST /api/scrape` з `{}` або
`{"mode": "sequential"}`; у відповіді — час кожної сторінки й помилки, якщо сторінка не завантажилась.

Крок 6: `rss.py` і зміни в `models.py` написав Claude Code (`claude -p`) за специфікацією `tests/unit/test_pravda.py`.
Рецензія його коду — `tests/unit/test_pravda_review.py`.

Розбір змін — [Крок 8 у книзі](https://nikoriakviktor.github.io/news_hub/tutorials/08_security/).
