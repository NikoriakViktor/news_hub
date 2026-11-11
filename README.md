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

| Крок | Папка | Що додається | Урок курсу |
|---|---|---|---|
| 1 | [`steps/01_typing_pydantic`](steps/01_typing_pydantic) | парсер з анотаціями типів, `NewsItem` на Pydantic | 37 |
| 2 | [`steps/02_fastapi_basics`](steps/02_fastapi_basics) | FastAPI: `GET /api/news`, `POST /api/scrape`, `/docs`, Postman | 38 |
| 3 | [`steps/03_sqlalchemy_alembic`](steps/03_sqlalchemy_alembic) | SQLAlchemy 2 async, унікальний `url`, CRUD, Alembic | 39 |
| 4 | [`steps/04_middleware_redis`](steps/04_middleware_redis) | middleware, кеш і rate limit на Redis, фоновий збір | 40 |
| 5 | [`steps/05_api_testing`](steps/05_api_testing) | тести: unit / integration, фікстури, моки, httpx, покриття | 42 |
| 6 | [`steps/06_ai_dev_tools`](steps/06_ai_dev_tools) | Claude Code у проєкті; RSS-джерело, написане AI за тестами | 43 |
| 7 | [`steps/07_llm_api`](steps/07_llm_api) | аналіз новин LLM: Gemini / Anthropic, Pydantic, кеш, circuit breaker | 44 |
| 8 | [`steps/08_security`](steps/08_security) | JWT адміна, bcrypt, завантаження URL без SSRF, підписані webhook | 47 |
| 9 | [`steps/09_telegram_bot`](steps/09_telegram_bot) | Telegram-бот на aiogram: команди, підписки, webhook | 48 |
| 10 | [`steps/10_docker`](steps/10_docker) | образ Docker: користувач без root, HEALTHCHECK, `/health/ready` | 49 |
| 11 | [`steps/11_compose_deploy`](steps/11_compose_deploy) | Compose: nginx, PostgreSQL, Redis, міграції, бот, бекап | 50 |
| 12 | [`steps/12_ci_cd`](steps/12_ci_cd) | CI/CD: тести ×2 Python, мінімальні версії, mypy, smoke, ghcr.io | 51 |

Ще два приклади для порівняння:

- [`examples/meteo_api`](examples/meteo_api) — REST API метеостанцій (дизайн REST, REST vs gRPC/GraphQL/WebSocket), урок 33;
- [`examples/fastapi_vs_drf`](examples/fastapi_vs_drf) — той самий API нотаток на FastAPI, щоб порівняти з DRF, урок 36.

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
mkdocs serve                       # → http://127.0.0.1:8000
```

## Звідки це

Код і тексти — з FastAPI-гілки курсу Python
[PY-Course-Victor-Nikoriak-11-11-2026](https://github.com/NikoriakViktor/PY-Course-Victor-Nikoriak-11-11-2026)
(уроки 33, 36–51). Django-версія тієї самої ідеї — книга
[Notes Chat App](https://nikoriakviktor.github.io/notes_chat_app/).
