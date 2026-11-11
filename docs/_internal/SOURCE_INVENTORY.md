# SOURCE_INVENTORY — звідки що в книзі

Курс: `PY-Course-Victor-Nikoriak-11-11-2026`. Сторінки уроків — `docs/modules/<m>/lesson_NN.md`.

## Код

| Джерело в курсі | У цьому репозиторії |
|---|---|
| `module_4/lessons/lesson_37_*/news_hub` | `steps/01_typing_pydantic` |
| `module_4/lessons/lesson_38_*/news_hub` | `steps/02_fastapi_basics` |
| `module_4/lessons/lesson_39_*/news_hub` | `steps/03_sqlalchemy_alembic` |
| `module_4/lessons/lesson_40_*/news_hub` | `steps/04_middleware_redis` |
| `module_4/lessons/lesson_42_*/news_hub` | `steps/05_api_testing` |
| `module_4/lessons/lesson_43_*/news_hub` | `steps/06_ai_dev_tools` |
| `module_4/lessons/lesson_44_*/news_hub` | `steps/07_llm_api` |
| `module_4/lessons/lesson_47_*/news_hub` | `steps/08_security` |
| `module_4/lessons/lesson_48_*/news_hub` | `steps/09_telegram_bot` |
| `module_5/lessons/lesson_49_*/news_hub` | `steps/10_docker` |
| `module_5/lessons/lesson_50_*/news_hub` | `steps/11_compose_deploy` |
| `module_5/lessons/lesson_51_*/news_hub` | `steps/12_ci_cd` |
| `module_4/lessons/lesson_33_rest_api_design/{meteo_api,weather_map,tests,Dockerfile,docker-compose.yml,requirements.txt}` | `examples/meteo_api` |
| `module_4/lessons/lesson_36_drf_fastapi/fastapi_notes.py` | `examples/fastapi_vs_drf/fastapi_notes.py` |
| `module_4/lessons/lesson_38_fastapi_basics/fastapi_demo` | `examples/fastapi_demo` |
| `module_6/lessons/lesson_52_final_project/patches/news_hub_search_index.patch` | лаба «Пошуковий індекс» (Практика) |

## Тексти: книга знань

| Сторінка книги | Джерело | Стан |
|---|---|---|
| `01_http_and_rest/api_styles.md` — Які бувають API | урок 33 «Які бувають API»; `examples/meteo_api/meteo_api/grpc_meteo.py`, `meteo.proto` | заплановано |
| `01_http_and_rest/rest_principles.md` — Принципи REST | урок 33 «REST: принципи» | заплановано |
| `01_http_and_rest/api_versioning.md` — Кейс: API v1 → v2 | урок 33 «Кейс: API v1 → v2», `meteo_api/legacy/` | заплановано |
| `01_http_and_rest/meteo_api.md` — Архітектура: API, клієнт і карта | урок 33 «Архітектура», `examples/meteo_api` | заплановано |
| `02_typing_and_pydantic/type_hints.md` — Анотації типів і `TypedDict` | урок 37 «Рефакторинг 1»; `steps/01/examples/before_dict.py`, `after_typed.py` | заплановано |
| `02_typing_and_pydantic/pydantic_models.md` — Моделі Pydantic | урок 37 «Рефакторинг 2»; `steps/01/news_hub/models.py` | заплановано |
| `02_typing_and_pydantic/trust_boundary.md` — Межа довіри | урок 37 «Архітектура: межа довіри» | заплановано |
| `03_fastapi_core/what_is_fastapi.md` — Що таке FastAPI | `fastapi_documentation.md` §1; урок 38 «Рефакторинг 1» | готово |
| `03_fastapi_core/routes_and_validation.md` — Маршрути, параметри і валідація | урок 38 «Рефакторинг 1», «Рефакторинг 3»; `steps/02/news_hub/api.py` | готово |
| `03_fastapi_core/dependencies.md` — Залежності: `Depends` і `lifespan` | урок 38 «Рефакторинг 2»; `fastapi_documentation.md` §5 | готово |
| `03_fastapi_core/openapi.md` — OpenAPI: опис API з коду | урок 38 «OpenAPI і /docs»; урок 33 | готово |
| `03_fastapi_core/fastapi_vs_drf.md` — FastAPI і Django REST Framework | урок 36 «Django + DRF чи FastAPI»; `examples/fastapi_vs_drf/fastapi_notes.py` | готово |
| `04_async/asgi_vs_wsgi.md` — ASGI і WSGI | `fastapi_documentation.md` §2 | заплановано |
| `04_async/endpoint_types.md` — Три типи ендпоінтів | `fastapi_documentation.md` §3 | заплановано |
| `04_async/blocking_code.md` — Блокуючий код: каскадний ефект | `fastapi_documentation.md` §4 | заплановано |
| `04_async/concurrent_scraping.md` — Паралельний збір і виміри | урок 38 «Async чи blocking: виміри»; `steps/02/news_hub/scraper.py` | заплановано |
| `05_databases/sqlalchemy_async.md` — SQLAlchemy 2 async: engine, сесії, таблиці | урок 39 «Рефакторинг 1»; `steps/03/news_hub/db.py`, `tables.py` | заплановано |
| `05_databases/repository_pattern.md` — Патерн Repository | урок 39 «Рефакторинг 2»; `fastapi_documentation.md` §7 | заплановано |
| `05_databases/session_per_request.md` — Сесія на запит і Unit of Work | урок 39 «Сесія на запит»; `fastapi_documentation.md` §8 | заплановано |
| `05_databases/crud.md` — Повний CRUD | урок 39 «Рефакторинг 3» | заплановано |
| `05_databases/alembic.md` — Міграції Alembic | урок 39 «Міграції Alembic»; `steps/03/migrations/` | заплановано |
| `05_databases/connection_pool.md` — Пул з'єднань | `fastapi_documentation.md` §6 | заплановано |
| `06_middleware_cache_jobs/middleware.md` — Middleware | урок 40 «Рефакторинг 1»; `steps/04/news_hub/middleware.py` | заплановано |
| `06_middleware_cache_jobs/redis_cache.md` — Кеш у Redis | урок 40 «Рефакторинг 2»; `steps/04/news_hub/cache.py` | заплановано |
| `06_middleware_cache_jobs/rate_limit.md` — Rate limit | урок 40 «Рефакторинг 3» | заплановано |
| `06_middleware_cache_jobs/background_jobs.md` — Фонові задачі | урок 40 «Рефакторинг 4»; `steps/04/news_hub/jobs.py` | заплановано |
| `07_testing/test_layers.md` — Шари тестів: unit і integration | урок 42 «Рефакторинг 1» | заплановано |
| `07_testing/fixtures.md` — Збережені сторінки й фікстури | урок 42 «Рефакторинг 2»; `steps/05/tests/fixtures/` | заплановано |
| `07_testing/mocks_and_fakes.md` — Мок і фейк мережі | урок 42 «Рефакторинг 3», «Рефакторинг 4» | заплановано |
| `07_testing/async_client.md` — API асинхронно: `httpx.AsyncClient` | урок 42 «Рефакторинг 5» | заплановано |
| `07_testing/coverage.md` — Покриття | урок 42 «Рефакторинг 6»; `.coveragerc` | заплановано |
| `07_testing/min_versions.md` — Мінімальні версії залежностей | урок 42 «Мінімальні версії залежностей» | заплановано |
| `08_security/jwt_admin.md` — Адмін, bcrypt і JWT | урок 47 «Рефакторинг 1»; `steps/08/news_hub/security.py` | заплановано |
| `08_security/ssrf.md` — SSRF: куди ходить сервер | урок 47 «Рефакторинг 2»; `steps/08/news_hub/safe_fetch.py` | заплановано |
| `08_security/signed_webhooks.md` — Підписані webhook | урок 47 «Рефакторинг 3»; `steps/08/news_hub/webhooks.py` | заплановано |
| `09_integrations/ai_dev_tools.md` — AI-інструменти розробника | урок 43; довідник `m4/ai/claude_code.md` | заплановано |
| `09_integrations/llm_api.md` — LLM API: інтерфейс, схема, промпт | урок 44 «Рефакторинг 1–4»; `steps/07/news_hub/llm.py`, `analysis.py` | заплановано |
| `09_integrations/llm_reliability.md` — Надійність і вартість LLM | урок 44 «Рефакторинг 5–6» | заплановано |
| `09_integrations/telegram_bot.md` — Telegram-бот на aiogram | урок 48; `steps/09/news_hub/bot/` | заплановано |
| `10_docker_and_ci/docker_image.md` — Docker-образ | урок 49; `steps/10/Dockerfile`, `.dockerignore` | заплановано |
| `10_docker_and_ci/compose.md` — Docker Compose | урок 50; `steps/11/docker-compose.yml`, `nginx/` | заплановано |
| `10_docker_and_ci/deploy.md` — Деплой на сервер | урок 50 «Деплой на сервер»; `fastapi_documentation.md` §10 | заплановано |
| `10_docker_and_ci/ci_cd.md` — CI/CD на GitHub Actions | урок 51; `.github/workflows/news_hub.yml` | заплановано |
| `10_docker_and_ci/microservices.md` — Мікросервіси: коли варто | `fastapi_documentation.md` §9 | заплановано |

## Тексти: Zero to Hero

| Сторінка | Джерело | Стан |
|---|---|---|
| `tutorials/01_typing_pydantic/index.md` | README кроку + урок 37 | скелет |
| `tutorials/01_typing_pydantic/*.md` — Анотації типів і `TypedDict`; Pydantic: модель `NewsItem`; Межа довіри | `m4/lesson_37.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/01_typing_pydantic/checkpoint.md` | урок 37 «Практика», «Підсумок» | заплановано |
| `tutorials/02_fastapi_basics/index.md` | README кроку + урок 38 | готово |
| `tutorials/02_fastapi_basics/` async_measurements.md, depends_and_lifespan.md, fastapi_app.md, openapi_and_postman.md, scrape_endpoint.md | `m4/lesson_38.md` «Рефакторинг …», «Архітектура», «Тести» | готово |
| `tutorials/02_fastapi_basics/checkpoint.md` | урок 38 «Практика», «Підсумок» | готово |
| `tutorials/03_sqlalchemy_alembic/index.md` | README кроку + урок 39 | скелет |
| `tutorials/03_sqlalchemy_alembic/*.md` — Engine, сесії й таблиця; Репозиторій замість `NewsStore`; Сесія на запит і COMMIT до відповіді; Повний CRUD; Міграції Alembic | `m4/lesson_39.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/03_sqlalchemy_alembic/checkpoint.md` | урок 39 «Практика», «Підсумок» | заплановано |
| `tutorials/04_middleware_redis/index.md` | README кроку + урок 40 | скелет |
| `tutorials/04_middleware_redis/*.md` — Middleware; Кеш стрічки в Redis; Rate limit: `429` і `Retry-After`; Фоновий збір: `202` і статус задачі | `m4/lesson_40.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/04_middleware_redis/checkpoint.md` | урок 40 «Практика», «Підсумок» | заплановано |
| `tutorials/05_api_testing/index.md` | README кроку + урок 42 | скелет |
| `tutorials/05_api_testing/*.md` — Шари тестів: unit і integration; Збережені сторінки замість рядків; Мок мережі: patch where used; Фейк замість моку: локальний HTTP-сервер; API асинхронно: `httpx.AsyncClient`; Покриття; Мінімальні версії залежностей | `m4/lesson_42.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/05_api_testing/checkpoint.md` | урок 42 «Практика», «Підсумок» | заплановано |
| `tutorials/06_ai_dev_tools/index.md` | README кроку + урок 43 | скелет |
| `tutorials/06_ai_dev_tools/*.md` — Проєкт, у якому AI може працювати; Експеримент: одне завдання — два запити; Рецензія AI-коду тестами | `m4/lesson_43.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/06_ai_dev_tools/checkpoint.md` | урок 43 «Практика», «Підсумок» | заплановано |
| `tutorials/07_llm_api/index.md` | README кроку + урок 44 | скелет |
| `tutorials/07_llm_api/*.md` — Один інтерфейс `LLMClient`; Асинхронний клієнт і пул моделей; JSON за схемою + Pydantic; Промпт: інструкція окремо, новина — як дані; Circuit breaker; База, кеш і вартість; Нові ендпоінти й тести | `m4/lesson_44.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/07_llm_api/checkpoint.md` | урок 44 «Практика», «Підсумок» | заплановано |
| `tutorials/08_security/index.md` | README кроку + урок 47 | скелет |
| `tutorials/08_security/*.md` — Адмін і JWT; SSRF: куди ходить сервер; Підписані webhook; Тести безпеки | `m4/lesson_47.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/08_security/checkpoint.md` | урок 47 «Практика», «Підсумок» | заплановано |
| `tutorials/09_telegram_bot/index.md` | README кроку + урок 48 | скелет |
| `tutorials/09_telegram_bot/*.md` — Бот над `news_hub`: фабрики, роутер, залежності; Відповідь у HTML: екранування і 4096; Підписки і сповіщення; Polling і webhook у FastAPI | `m4/lesson_48.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/09_telegram_bot/checkpoint.md` | урок 48 «Практика», «Підсумок» | заплановано |
| `tutorials/10_docker/index.md` | README кроку + урок 49 | скелет |
| `tutorials/10_docker/*.md` — Що потрапляє в образ; Шари й кеш; Користувач, дані й змінні середовища; Здоров'я і зупинка | `m5/lesson_49.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/10_docker/checkpoint.md` | урок 49 «Практика», «Підсумок» | заплановано |
| `tutorials/11_compose_deploy/index.md` | README кроку + урок 50 | скелет |
| `tutorials/11_compose_deploy/*.md` — Порядок запуску: healthy, а не «запущено»; nginx і справжній IP клієнта; Секрети в `.env`; Зовнішній сервіс не зупиняє старт; Деплой на сервер | `m5/lesson_50.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/11_compose_deploy/checkpoint.md` | урок 50 «Практика», «Підсумок» | заплановано |
| `tutorials/12_ci_cd/index.md` | README кроку + урок 51 | скелет |
| `tutorials/12_ci_cd/*.md` — Коли CI запускається; Що саме перевіряти; Порядок і паралельність; Права, секрети, публікація | `m5/lesson_51.md` «Рефакторинг …», «Архітектура», «Тести» | заплановано |
| `tutorials/12_ci_cd/checkpoint.md` | урок 51 «Практика», «Підсумок» | заплановано |

## Інші розділи

| Сторінка | Джерело | Стан |
|---|---|---|
| `deep_dive/*` | код `steps/12_ci_cd`, README і CLAUDE.md кроку 12 | заплановано |
| `labs/*` | «Практика» уроків 33, 36–51; урок 52 + патч пошукового індексу | заплановано |
| `reference/fastapi_reference.md` | `m4/fastapi/fastapi_documentation.md` (§1–11, чекліст) | заплановано |
| `reference/django_to_fastapi.md` | урок 36, `examples/fastapi_vs_drf` | заплановано |
| `reference/claude_code.md` | `m4/ai/claude_code.md` | заплановано |
| `reference/glossary.md`, `reference/troubleshooting.md` | терміни й «Типові помилки» уроків | заплановано |
| `TEACHING_GUIDE.md` | відповідність кроків урокам | скелет |

Не переносимо: кнопки Colab, посилання на ноутбуки, домашні завдання курсу.
