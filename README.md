# News Hub — книга про FastAPI

Новинний агрегатор на **FastAPI**, зібраний крок за кроком: від парсера з анотаціями типів до образу Docker,
Compose зі стеком nginx → API → PostgreSQL + Redis і CI/CD на GitHub Actions.

📖 **Книга:** <https://nikoriakviktor.github.io/news_hub/>

```
rbc.ua / RSS → парсер → NewsItem (Pydantic) → PostgreSQL / SQLite (SQLAlchemy 2 async)
     → кеш Redis → FastAPI → аналіз LLM (Gemini / Anthropic) → Telegram-бот → Docker → Compose → CI/CD
```

## Кроки

Кожна папка `steps/NN_*` — **повний робочий проєкт** на цьому кроці зі своїми тестами.
Наступний крок = попередній + зміни, тож різницю між кроками видно одною командою:

```bash
git diff --no-index steps/04_middleware_redis steps/05_api_testing
```

| Крок | Папка | Що додається |
|---|---|---|
| 1 | [`steps/01_typing_pydantic`](steps/01_typing_pydantic) | парсер з анотаціями типів, `NewsItem` на Pydantic |
| 2 | [`steps/02_fastapi_basics`](steps/02_fastapi_basics) | FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman |
| 3 | [`steps/03_sqlalchemy_alembic`](steps/03_sqlalchemy_alembic) | SQLAlchemy 2 async, унікальний `url`, CRUD, Alembic |
| 4 | [`steps/04_middleware_redis`](steps/04_middleware_redis) | middleware, кеш і rate limit на Redis, фоновий збір |
| 5 | [`steps/05_api_testing`](steps/05_api_testing) | тести: unit / integration, фікстури, моки, httpx, покриття |
| 6 | [`steps/06_ai_dev_tools`](steps/06_ai_dev_tools) | Claude Code у проєкті; RSS-джерело, написане AI за тестами |
| 7 | [`steps/07_llm_api`](steps/07_llm_api) | аналіз новин LLM: Gemini / Anthropic, Pydantic, кеш, circuit breaker |
| 8 | [`steps/08_security`](steps/08_security) | JWT адміна, bcrypt, завантаження URL без SSRF, підписані webhook |
| 9 | [`steps/09_telegram_bot`](steps/09_telegram_bot) | Telegram-бот на aiogram: команди, підписки, webhook |
| 10 | [`steps/10_docker`](steps/10_docker) | образ Docker: користувач без root, HEALTHCHECK, `/health/ready` |
| 11 | [`steps/11_compose_deploy`](steps/11_compose_deploy) | Compose: nginx, PostgreSQL, Redis, міграції, бот, бекап |
| 12 | [`steps/12_ci_cd`](steps/12_ci_cd) | CI/CD: тести ×2 Python, мінімальні версії, mypy, smoke, ghcr.io |

Ще приклади:

- [`examples/meteo_api`](examples/meteo_api) — REST API метеостанцій (дизайн REST, REST vs gRPC/GraphQL/WebSocket);
- [`examples/fastapi_vs_drf`](examples/fastapi_vs_drf) — той самий API нотаток на FastAPI, щоб порівняти з DRF;
- [`examples/frameworks_compared`](examples/frameworks_compared) — той самий API на FastAPI, Flask і Django;
- [`examples/http_anatomy`](examples/http_anatomy) — HTTP зсередини: сирий запит, методи, коди, кеш;
- [`examples/pagination`](examples/pagination) — фільтри, сортування, offset проти курсора на мільйоні рядків;
- [`examples/versioning`](examples/versioning) — версії в шляху, заголовку й параметрі; Deprecation і Sunset;
- [`examples/realtime`](examples/realtime) — SSE (`fastapi.sse`), WebSocket з токеном і розсилкою, `app.webhooks` в OpenAPI;
- [`examples/cors`](examples/cors) — `CORSMiddleware`: preflight, небезпека `["*"]` з credentials, порядок middleware;
- [`examples/errors`](examples/errors) — помилки у форматі RFC 9457 (Problem Details) і типові пастки власних обробників;
- [`examples/fastapi_demo`](examples/fastapi_demo) — шість ендпоінтів і навантажувальний тест: що блокує сервер.

## Швидкий старт

```bash
git clone https://github.com/NikoriakViktor/news_hub.git
cd news_hub/steps/02_fastapi_basics
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q
uvicorn news_hub.api:app --reload  # → http://127.0.0.1:8000/docs
```

Як запускати кожен крок (база, Redis, Docker) — README в папці кроку та розділ «Як користуватися» в книзі.

## Книга локально

```bash
pip install -r requirements-docs.txt
python -m mkdocs serve             # → http://127.0.0.1:8000
```

## Див. також

Django-версія тієї самої ідеї — книга [Notes Chat App](https://nikoriakviktor.github.io/notes_chat_app/).
