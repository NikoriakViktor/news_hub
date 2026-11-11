# Крок 7. Аналіз новин через LLM API

> **Код кроку:** [`steps/07_llm_api`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/07_llm_api).
>
> **Передумови:** [Крок 6. AI-інструменти розробника](../06_ai_dev_tools/index.md).

## Що додаємо

Кожна новина отримує підсумок, тему, тональність і ключові слова від Gemini або Anthropic за спільним інтерфейсом `LLMClient`. Відповідь перевіряє Pydantic, повтори відсікає кеш, а circuit breaker не дає засипати запитами провайдера, який лежить.

## Теми кроку

1. Один інтерфейс `LLMClient`
2. Асинхронний клієнт і пул моделей
3. JSON за схемою + Pydantic
4. Промпт: інструкція окремо, новина — як дані
5. Circuit breaker
6. База, кеш і вартість
7. Нові ендпоінти й тести

!!! info "Сторінки кроку — у роботі"
    Покроковий розбір цих тем з'явиться тут. Поки що — код кроку, README в його папці й теорія:
    [Частина IX. Інтеграції: AI, LLM, Telegram](../../09_integrations/README.md).

## Структура після кроку

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
│   └── api.py        ← FastAPI: /api/news (+ CRUD, кеш), /stats, POST /api/scrape, /api/scrape/jobs,
│                       POST /api/news/{id}/analyze, /api/analyze/jobs
├── data/rbc_news_snapshot.json   ← 168 новин, зібраних parse_rbc_news
├── migrations/       ← крок 3: Alembic — версії схеми бази (0001: таблиця news; 0002: колонки аналізу LLM)
├── alembic.ini
├── docker-compose.yml ← PostgreSQL 16 (крок 3) і Redis 7 (крок 4) для розробки
├── postman/news_hub.postman_collection.json   ← 16 запитів з перевірками
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
    │                   скрапер проти локального aiohttp-сервера; test_analyze_api.py — аналіз LLM через API
    └── live/         ← крок 7: справжні виклики моделі — лише pytest -m llm (потрібен ключ і мережа)
```

## Запуск

Усі команди — з папки кроку: `cd steps/07_llm_api`.

```bash
pip install -r requirements.txt
pytest                      # 168 тестів: SQLite у пам'яті + fakeredis + локальний aiohttp-сервер + FakeLLM
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

Swagger: `POST /api/scrape` (`{"source": "snapshot"}`) → `POST /api/news/1/analyze` → `POST /api/analyze/jobs`
(`{"limit": 20}`) → `GET /api/news/stats` (поля `ai_category`, `sentiment`) → `GET /api/news?sentiment=негативна`.

Ті самі тести на справжніх серверах: `TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test TEST_REDIS_URL=redis://localhost:6379/15 pytest` (базу `news_hub_test` створи заздалегідь; Redis-база 15 очищується перед кожним тестом). Лише так ловиться гонка в rate limit: fakeredis не віддає керування циклу подій, тож одночасних запитів на ньому не буває (`tests/integration/test_async_api.py`).

- http://127.0.0.1:8000/docs — Swagger UI: спершу `POST /api/scrape` з `{"source": "snapshot"}`, потім `GET /api/news`;
- Postman: Import → `postman/news_hub.postman_collection.json` → Run collection;
- без Postman: `npx newman run postman/news_hub.postman_collection.json`.

Свіжа стрічка (коли `www.rbc.ua` доступний з мережі) — `POST /api/scrape` з `{}` або
`{"mode": "sequential"}`; у відповіді — час кожної сторінки й помилки, якщо сторінка не завантажилась.

Крок 6: `rss.py` і зміни в `models.py` написав Claude Code (`claude -p`) за специфікацією `tests/unit/test_pravda.py`.
Рецензія його коду — `tests/unit/test_pravda_review.py`.

## Порівняння з попереднім кроком

```bash
git diff --no-index --stat steps/06_ai_dev_tools steps/07_llm_api
git diff --no-index steps/06_ai_dev_tools/news_hub steps/07_llm_api/news_hub
```

## Що далі

[Крок 8. Безпека: JWT, SSRF, webhook](../08_security/index.md)
