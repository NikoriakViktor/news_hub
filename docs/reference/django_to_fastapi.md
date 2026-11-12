# Від Django до FastAPI

Таблиця відповідностей для тих, хто знає Django і DRF. Праворуч — як це зроблено в News Hub
(`steps/12_ci_cd`). Той самий API нотаток на обох фреймворках і розбір відмінностей —
[FastAPI і Django REST Framework](../03_fastapi_core/fastapi_vs_drf.md); теми Django — у
[Django-книзі](https://nikoriakviktor.github.io/notes_chat_app/).

Головна різниця: Django дає готові частини (ORM, адмінку, вхід, налаштування), FastAPI — лише HTTP-шар, перевірку
даних і впровадження залежностей. Решту обираєш сам: у News Hub це SQLAlchemy 2 + Alembic, PyJWT + bcrypt, Redis,
pytest.

## Проєкт і запуск { #project }

| Django / DRF | FastAPI / News Hub | Докладно |
|---|---|---|
| `django-admin startproject`, `startapp` | пакет Python: `news_hub/api.py` (застосунок), `db.py`, `tables.py`, `repository.py`, … | [структура кроку 3](../tutorials/03_sqlalchemy_alembic/index.md) |
| `manage.py runserver` | `uvicorn news_hub.api:app --reload` | [Команди](commands.md#run) |
| WSGI (`wsgi.py`), Gunicorn | ASGI, uvicorn | [Архітектура](architecture.md#asgi-wsgi) |
| `INSTALLED_APPS` | імпорти й `app.include_router(...)` | [Шпаргалка FastAPI](fastapi_cheatsheet.md#router) |
| `AppConfig.ready()`, сигнал старту | `lifespan` | [`lifespan`](../03_fastapi_core/dependencies.md#lifespan) |
| `manage.py <команда>` | модуль з `if __name__ == "__main__"`: `python -m news_hub.security`, `python -m news_hub.bot` | [Команди](commands.md#scripts) |
| `manage.py shell` | `python`, потім `from news_hub... import ...` | — |

Django-книга: [структура проєкту](https://nikoriakviktor.github.io/notes_chat_app/02_django_core/project_structure_full/),
[management-команди](https://nikoriakviktor.github.io/notes_chat_app/02_django_core/management_commands_full/).

## Адреси й обробники { #urls-views }

| Django / DRF | FastAPI | Докладно |
|---|---|---|
| `urls.py`: `path("api/news/<int:pk>/", view)` | `@app.get("/api/news/{news_id}")` над функцією; тип — з анотації `news_id: int` | [Маршрути](../03_fastapi_core/routes_and_validation.md) |
| `include("app.urls")` з префіксом | `APIRouter(prefix="/api/news")` + `app.include_router(router)` | [Шпаргалка FastAPI](fastapi_cheatsheet.md#router) |
| function view / `APIView` | функція-ендпоінт (`def` або `async def`) | [Що таке FastAPI](../03_fastapi_core/what_is_fastapi.md) |
| `ViewSet` + `DefaultRouter` | окрема функція на кожен метод і шлях | [FastAPI і DRF](../03_fastapi_core/fastapi_vs_drf.md#mapping) |
| `@action(detail=True)` | ще один маршрут: `POST /api/news/{news_id}/analyze` | — |
| `request.GET["q"]`, `request.query_params` | параметр функції `q: str = Query(...)` | [Параметри](fastapi_cheatsheet.md#params) |
| `request.data` | модель Pydantic у сигнатурі: `body: NewsCreate` | [Маршрути](../03_fastapi_core/routes_and_validation.md) |
| `get_object_or_404(News, pk=pk)` | залежність `get_news_or_404` → `RowDep` | `news_hub/api.py` |
| `Response(data, status=201)` | `return obj` + `status_code=201` у декораторі | [Відповіді](fastapi_cheatsheet.md#responses) |
| `raise NotFound(...)` / `Http404` | `raise HTTPException(404, detail=...)` | [Коди News Hub](http_status_codes.md) |
| `APPEND_SLASH` | маршрут без `/` у кінці; `/api/news/` → `307` | [Шпаргалка FastAPI](fastapi_cheatsheet.md#routes) |

Django-книга: [маршрутизація](https://nikoriakviktor.github.io/notes_chat_app/02_django_core/url_routing_full/),
[views](https://nikoriakviktor.github.io/notes_chat_app/02_django_core/views_full/),
[DRF](https://nikoriakviktor.github.io/notes_chat_app/06_application_architecture/drf_rest_api_full/).

## Дані й перевірка { #serializers }

| Django / DRF | FastAPI / Pydantic | Докладно |
|---|---|---|
| `Serializer` для входу | модель запиту: `NewsCreate`, `NewsPatch`, `ScrapeRequest` | [Моделі Pydantic](../02_typing_and_pydantic/pydantic_models.md) |
| `ModelSerializer` для виходу, `fields = [...]` | модель відповіді `NewsOut` + `response_model`; `from_attributes=True` для рядка SQLAlchemy | [`from_attributes`](../02_typing_and_pydantic/config_dict.md#from-attributes) |
| `serializer.is_valid(raise_exception=True)` | автоматично до виклику функції | [Маршрути](../03_fastapi_core/routes_and_validation.md) |
| помилки валідації: `400`, `{"поле": ["…"]}` | `422`, `{"detail": [{"loc", "msg", "type"}]}` | [`400` чи `422`](../01_http_and_rest/status_codes.md#400-vs-422) |
| `validate_<поле>()` | `@field_validator("поле")` | [Валідатори](../02_typing_and_pydantic/validators.md) |
| `validate()` (кілька полів) | `@model_validator(mode="after")` | [Валідатори](../02_typing_and_pydantic/validators.md) |
| `SerializerMethodField`, `source="…"` | `@computed_field` | [Валідатори](../02_typing_and_pydantic/validators.md) |
| `partial=True` | окрема модель з усіма `None` + `model_dump(exclude_unset=True)` | [`exclude_unset`](../02_typing_and_pydantic/pydantic_models.md#exclude-unset) |
| `read_only_fields` | поля, яких немає в моделі запиту | [масове присвоєння](../02_typing_and_pydantic/config_dict.md#mass-assignment) |
| Django Forms | `Form()` у параметрах (для HTML-форм); API приймає JSON | [Параметри](fastapi_cheatsheet.md#params) |

Django-книга: [серіалізатори](https://nikoriakviktor.github.io/notes_chat_app/06_application_architecture/django_serializers_full/),
[форми](https://nikoriakviktor.github.io/notes_chat_app/04_forms_and_validation/django_forms_full/).

## ORM і міграції { #orm }

| Django ORM | SQLAlchemy 2 (async) / Alembic | Докладно |
|---|---|---|
| `class News(models.Model)` | `class NewsRow(Base)` з `Mapped[...] = mapped_column(...)` — `news_hub/tables.py` | [Engine і таблиця](../tutorials/03_sqlalchemy_alembic/engine_and_table.md) |
| `CharField(max_length=300)` | `mapped_column(String(300))` | — |
| `unique=True` → `IntegrityError` | те саме; у News Hub `IntegrityError` → `409` | [CRUD](../tutorials/03_sqlalchemy_alembic/crud.md) |
| `News.objects.filter(lang="uk")[:50]` | `select(NewsRow).where(NewsRow.lang == "uk").limit(50)` + `await session.scalars(stmt)` | [Репозиторій](../tutorials/03_sqlalchemy_alembic/repository.md) |
| `title__icontains=q` | `NewsRow.title.icontains(q, autoescape=True)` | `news_hub/repository.py` |
| `.values("lang").annotate(Count("id"))` | `select(column, func.count()).group_by(column)` | `NewsRepository.stats` |
| `.get(pk=1)` | `await session.get(NewsRow, 1)` | `BaseRepository.get` |
| `select_related` / `prefetch_related` | `joinedload` / `selectinload`; лінивий зв'язок в async → `MissingGreenlet` | [`from_attributes` і SQLAlchemy](../02_typing_and_pydantic/config_dict.md#from-attributes) |
| `transaction.atomic()`, `ATOMIC_REQUESTS` | сесія на запит `get_db`: `COMMIT` або `ROLLBACK` | [Сесія на запит](../tutorials/03_sqlalchemy_alembic/session_per_request.md) |
| `save()` | `session.add(obj)`, `await session.flush()` (SQL зараз), `COMMIT` — у `get_db` | [`flush`](../tutorials/03_sqlalchemy_alembic/session_per_request.md#flush) |
| `DATABASES` у `settings.py` | `DATABASE_URL` → `create_async_engine(...)` | [Змінні середовища](env_vars.md) |
| `makemigrations` | `alembic revision --autogenerate -m "…"` (і **прочитати** міграцію) | [Міграції Alembic](../tutorials/03_sqlalchemy_alembic/alembic.md) |
| `migrate` | `alembic upgrade head` | [Команди](commands.md#alembic) |
| `makemigrations --check` | `alembic check` (у CI) | [крок 12](../tutorials/12_ci_cd/what_to_check.md) |

Django-книга: [ORM](https://nikoriakviktor.github.io/notes_chat_app/03_database_and_orm/django_orm_full/),
[міграції](https://nikoriakviktor.github.io/notes_chat_app/03_database_and_orm/django_migrations_full/),
[транзакції](https://nikoriakviktor.github.io/notes_chat_app/03_database_and_orm/transactions_concurrency_full/).
Повністю — [Частина V](../05_databases/README.md).

## Вхід і права { #auth }

| Django / DRF | FastAPI / News Hub | Докладно |
|---|---|---|
| `django.contrib.auth`, `User` | немає; один адмін з `ADMIN_USERNAME` і bcrypt-хешем `ADMIN_PASSWORD_HASH` | [Адмін і JWT](../tutorials/08_security/admin_jwt.md) |
| сесія в cookie, `login()` | `POST /api/admin/token` → JWT, далі `Authorization: Bearer …` | [Адмін і JWT](../tutorials/08_security/admin_jwt.md) |
| `request.user` | значення залежності: `require_admin` повертає `sub` з токена | [Залежності](../03_fastapi_core/dependencies.md) |
| `permission_classes = [IsAuthenticated]` | `dependencies=[AdminDep]` на ендпоінті | `news_hub/security.py` |
| `@login_required`, `IsAdminUser` | та сама залежність: `401` без токена, `403` без ролі `admin` | [Коди News Hub](http_status_codes.md) |
| `make_password`, `PASSWORD_HASHERS` | `bcrypt` напряму (`hash_password`, `authenticate`) | `news_hub/security.py` |
| CSRF-захист | для `Bearer`-токена не потрібен; для cookie — `SameSite` і CSRF-токен | [CORS](../06_middleware_cache_jobs/cors.md#credentials) |
| `django-cors-headers` | `CORSMiddleware` | [CORS](../06_middleware_cache_jobs/cors.md) |
| DRF throttling | `rate_limit` middleware на Redis: `429` + `Retry-After` | [Rate limit](../tutorials/04_middleware_redis/rate_limit.md) |

Django-книга: [вхід, сесії, права](https://nikoriakviktor.github.io/notes_chat_app/07_auth_and_security/auth_sessions_permissions/),
[права DRF](https://nikoriakviktor.github.io/notes_chat_app/07_auth_and_security/permissions_full/).
Повністю — [Частина VIII](../08_security/README.md).

## Налаштування { #settings }

| Django | FastAPI / News Hub | Докладно |
|---|---|---|
| `settings.py` з константами | змінні середовища: `os.getenv(...)` у модулях і `load_*_settings()` | [Змінні середовища](env_vars.md) |
| `django-environ`, `.env` | `pydantic-settings` (`BaseSettings`) — або `os.getenv`, як у News Hub | [Налаштування](../02_typing_and_pydantic/settings.md) |
| `DEBUG = True` | `uvicorn --reload` лише в розробці; `/docs` доступна завжди | — |
| `ImproperlyConfigured` при старті | `RuntimeError` з `load_admin_settings()` у `lifespan`: застосунок не стартує | [крок 8](../tutorials/08_security/checkpoint.md#mistakes) |

Django-книга: [змінні середовища й секрети](https://nikoriakviktor.github.io/notes_chat_app/10_linux_and_devops/linux_08_environment_variables_and_secrets_full/).

## Адмінка, шаблони, статика { #admin }

| Django | FastAPI | У News Hub |
|---|---|---|
| `django.contrib.admin` | немає; окремі пакети (SQLAdmin тощо) або свої ендпоінти | ендпоінти з `AdminDep`, Swagger UI як інтерфейс |
| шаблони (`render`) | `Jinja2Templates` зі Starlette | немає: лише JSON API |
| `staticfiles` | `StaticFiles` зі Starlette, у production — nginx | немає |
| Browsable API | `/docs` (Swagger UI), `/redoc` | `/docs` |
| `drf-spectacular` | `/openapi.json` з коробки | [OpenAPI](../03_fastapi_core/openapi.md) |

Django-книга: [адмінка](https://nikoriakviktor.github.io/notes_chat_app/05_frontend_and_templates/django_admin_full/).

## Middleware, кеш, фонові задачі { #middleware }

| Django | FastAPI / News Hub | Докладно |
|---|---|---|
| `MIDDLEWARE = [...]` (зверху — зовнішній) | `app.middleware("http")(fn)`: **останній** зареєстрований — зовнішній | [Middleware](../tutorials/04_middleware_redis/middleware.md) |
| cache framework, `cache_page` | `NewsCache` на Redis: cache-aside, версія для інвалідації | [Кеш](../tutorials/04_middleware_redis/cache.md) |
| Celery, `django-tasks` | `BackgroundTasks` + статус задачі в Redis (`JobStore`) | [Фоновий збір](../tutorials/04_middleware_redis/background_jobs.md) |
| сигнали (`post_save`) | явний виклик після дії: `background.add_task(notifier, new)` | [Підписки й сповіщення](../tutorials/09_telegram_bot/subscriptions_notify.md) |

Django-книга: [фонові задачі](https://nikoriakviktor.github.io/notes_chat_app/06_application_architecture/django_tasks_full/).
Повністю — [Частина VI](../06_middleware_cache_jobs/README.md).

## Async і реальний час { #channels }

| Django | FastAPI | Докладно |
|---|---|---|
| async views, `sync_to_async` | `async def` — звичайний ендпоінт; блокуюче — у `def` або `run_in_threadpool` | [Архітектура](architecture.md#blocking) |
| Channels, consumers, `channel_layers` | `@app.websocket(...)`; між процесами — Redis Pub/Sub | [WebSocket](../01_http_and_rest/api_styles.md#websocket) |
| SSE через `StreamingHttpResponse` | `fastapi.sse.EventSourceResponse` (FastAPI ≥ 0.135) | [SSE](../01_http_and_rest/api_styles.md#sse) |

Django-книга: [Channels і WebSocket](https://nikoriakviktor.github.io/notes_chat_app/09_async_and_realtime/channels_websocket/),
[ASGI](https://nikoriakviktor.github.io/notes_chat_app/09_async_and_realtime/async_03_asgi_full/).

## Тести { #tests }

| Django / DRF | FastAPI / News Hub | Докладно |
|---|---|---|
| `manage.py test`, `TestCase` | `pytest`, фікстури в `conftest.py` | [Шари тестів](../tutorials/05_api_testing/test_layers.md) |
| тестова база створюється сама | `TEST_DATABASE_URL` (за замовчуванням SQLite у пам'яті) + `dependency_overrides[get_db]` | [тестова база](../tutorials/03_sqlalchemy_alembic/session_per_request.md#test-db) |
| `APIClient`, `force_authenticate` | `TestClient(app)` + справжній токен з `/api/admin/token` або підміна залежності | [Тести безпеки](../tutorials/08_security/security_tests.md) |
| `mock.patch` зовнішніх API | фейки: `FakeLLM`, fakeredis, локальний HTTP-сервер, двійник Telegram | [Фейк замість моку](../tutorials/05_api_testing/fake_server.md) |

Django-книга: [тестування Django](https://nikoriakviktor.github.io/notes_chat_app/08_testing_and_quality/django_testing_full/),
[pytest](https://nikoriakviktor.github.io/notes_chat_app/08_testing_and_quality/pytest_basics_full/).

## Деплой { #deploy }

| Django | FastAPI / News Hub | Докладно |
|---|---|---|
| Gunicorn + nginx | uvicorn + nginx | [Деплой](../tutorials/11_compose_deploy/deploy.md) |
| `collectstatic` | немає статики | — |
| `migrate` при деплої | окремий сервіс `migrate` у Compose до старту `api` | [Порядок запуску](../tutorials/11_compose_deploy/startup_order.md) |
| `SECURE_PROXY_SSL_HEADER`, `USE_X_FORWARDED_HOST` | `FORWARDED_ALLOW_IPS` для uvicorn | [nginx і IP клієнта](../tutorials/11_compose_deploy/nginx_real_ip.md) |

Django-книга: [nginx, Gunicorn, uvicorn](https://nikoriakviktor.github.io/notes_chat_app/11_deployment/deploy_12_nginx_gunicorn_uvicorn_full/).

## Що обрати { #choose }

Схема вибору й приклад — [FastAPI і DRF: як обрати](../03_fastapi_core/fastapi_vs_drf.md#how-to-choose). Коротко:
сайт, адмінка й користувачі над однією базою — Django + DRF; окремий API-сервіс з великою кількістю мережевого
I/O (як News Hub: сайти, LLM, Telegram) — FastAPI.
