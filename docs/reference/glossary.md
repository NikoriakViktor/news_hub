# Глосарій

Терміни книги: коротке означення і де розібрано. Латинські — за абеткою, далі українські. Терміни Django —
у [глосарії Django-книги](https://nikoriakviktor.github.io/notes_chat_app/GLOSSARY/).

## A–Z { #latin }

| Термін | Що це | Де |
|---|---|---|
| **Alembic** | міграції схеми для SQLAlchemy: `revision --autogenerate`, `upgrade head`, `check` | [крок 3](../tutorials/03_sqlalchemy_alembic/alembic.md) |
| **`Annotated`** | `Annotated[T, метадані]`: тип першим, далі `Query(...)`, `Depends(...)`, `Field(...)` | [Анотації типів](../02_typing_and_pydantic/type_hints.md#annotated) |
| **API Gateway** | точка входу перед кількома сервісами: TLS, маршрутизація, ліміти | [Архітектура](architecture.md#microservices) |
| **APIRouter** | група маршрутів зі спільним префіксом, тегами й залежностями | [Шпаргалка FastAPI](fastapi_cheatsheet.md#router) |
| **ASGI** | інтерфейс між async-сервером (uvicorn) і застосунком (FastAPI): HTTP, WebSocket, lifespan | [Архітектура](architecture.md#asgi-wsgi) |
| **`BackgroundTasks`** | функції, які FastAPI виконує в тому самому процесі після відправлення відповіді | [крок 4](../tutorials/04_middleware_redis/background_jobs.md) |
| **bcrypt** | повільний хеш пароля з сіллю і кількістю раундів (`$2b$12$…`) | [крок 8](../tutorials/08_security/admin_jwt.md) |
| **BFF** | Backend for Frontend: сервіс, що збирає дані кількох сервісів для одного клієнта | [Архітектура](architecture.md#microservices) |
| **cache-aside** | спершу кеш; немає — база, і результат кладемо в кеш | [крок 4](../tutorials/04_middleware_redis/cache.md) |
| **CI/CD** | автоматична перевірка кожної зміни (CI) і публікація результату (CD) | [крок 12](../tutorials/12_ci_cd/index.md) |
| **circuit breaker** | після N збоїв поспіль перестає кликати провайдера на час `T` і одразу відповідає `503` | [крок 7](../tutorials/07_llm_api/circuit_breaker.md) |
| **CORS** | правила браузера, яким сайтам дозволено читати відповіді API; сервер дозволяє заголовками `Access-Control-*` | [CORS](../06_middleware_cache_jobs/cors.md) |
| **`Depends`** | оголошення залежності: FastAPI викликає функцію й передає результат в ендпоінт | [Залежності](../03_fastapi_core/dependencies.md) |
| **DI** | Dependency Injection: код отримує ресурси ззовні, а не створює сам — тому їх легко підмінити в тестах | [Залежності](../03_fastapi_core/dependencies.md) |
| **`dependency_overrides`** | словник «залежність → підміна» для тестів | [Шпаргалка FastAPI](fastapi_cheatsheet.md#depends) |
| **event loop** | цикл подій: один потік перемикає корутини, поки вони чекають I/O | [Архітектура](architecture.md#endpoint-types) |
| **`exclude_unset`** | `model_dump(exclude_unset=True)` — лише поля, які клієнт передав; основа `PATCH` | [Моделі Pydantic](../02_typing_and_pydantic/pydantic_models.md#exclude-unset) |
| **fakeredis** | Redis у пам'яті процесу для тестів; `REDIS_URL=fakeredis://` | [крок 4](../tutorials/04_middleware_redis/index.md) |
| **`FakeLLM`** | клієнт LLM без мережі з передбачуваними відповідями; `LLM_PROVIDER=fake` | [крок 7](../tutorials/07_llm_api/llm_client.md) |
| **`flush`** | надіслати SQL у базу зараз (отримати `id`, помилки обмежень), `COMMIT` — пізніше | [крок 3](../tutorials/03_sqlalchemy_alembic/session_per_request.md#flush) |
| **`from_attributes`** | Pydantic будує модель з атрибутів об'єкта (рядка SQLAlchemy) | [`ConfigDict`](../02_typing_and_pydantic/config_dict.md#from-attributes) |
| **healthcheck** | команда, якою Docker перевіряє контейнер; у News Hub — `/health` (образ) і `/health/ready` (Compose) | [крок 10](../tutorials/10_docker/health_shutdown.md) |
| **HMAC** | підпис повідомлення спільним секретом: `sha256=<hex>` від часу й тіла | [крок 8](../tutorials/08_security/webhooks.md) |
| **IDOR** | доступ до чужого об'єкта підстановкою його `id`; захист — шукати серед своїх, чужий → `404` | [Колекції](../01_http_and_rest/collections.md#security) |
| **idempotency** | повтор запиту дає той самий стан, що й один запит: `GET`, `PUT`, `DELETE` — так, `POST` — ні | [Методи HTTP](../01_http_and_rest/http_methods.md) |
| **`Idempotency-Key`** | заголовок, за яким сервер розпізнає повтор того самого `POST` | [Методи HTTP](../01_http_and_rest/http_methods.md) |
| **JSON Schema** | опис структури JSON; Pydantic генерує її для OpenAPI і для відповіді LLM | [крок 7](../tutorials/07_llm_api/json_schema.md) |
| **JWT** | підписаний токен `заголовок.дані.підпис`; News Hub перевіряє `exp`, `sub`, `role` | [крок 8](../tutorials/08_security/admin_jwt.md) |
| **lax / strict** | режими Pydantic: перетворювати `"5"` на `5` чи ні | [lax і strict](../02_typing_and_pydantic/strict_mode.md) |
| **`lifespan`** | код запуску й зупинки застосунку: до `yield` і після | [Залежності](../03_fastapi_core/dependencies.md#lifespan) |
| **liveness / readiness** | «процес живий» (`/health`) і «готовий обслуговувати: база й Redis доступні» (`/health/ready`) | [крок 10](../tutorials/10_docker/health_shutdown.md) |
| **LLM** | велика мовна модель; у News Hub — Gemini або Anthropic за інтерфейсом `LLMClient` | [крок 7](../tutorials/07_llm_api/index.md) |
| **mass assignment** | клієнт задає поля, яких не мав би (`is_admin`), бо тіло копіюється в модель цілком | [`ConfigDict`](../02_typing_and_pydantic/config_dict.md#mass-assignment) |
| **middleware** | код навколо кожного запиту: бачить запит до ендпоінта і відповідь після | [крок 4](../tutorials/04_middleware_redis/middleware.md) |
| **`MissingGreenlet`** | помилка SQLAlchemy async: лінивий зв'язок завантажується поза `await` | [`ConfigDict`](../02_typing_and_pydantic/config_dict.md#from-attributes) |
| **mock / fake** | мок підміняє виклик і перевіряє, як його викликали; фейк — робоча спрощена реалізація | [крок 5](../tutorials/05_api_testing/fake_server.md) |
| **OpenAPI** | машинний опис API (`/openapi.json`), з якого будуються `/docs` і клієнти | [OpenAPI](../03_fastapi_core/openapi.md) |
| **PID 1** | перший процес контейнера; саме він отримує `SIGTERM` від `docker stop` | [крок 10](../tutorials/10_docker/health_shutdown.md) |
| **polling / webhook (Telegram)** | бот сам питає `getUpdates` / Telegram надсилає update на HTTPS-адресу | [крок 9](../tutorials/09_telegram_bot/polling_webhook.md) |
| **preflight** | запит `OPTIONS`, яким браузер питає дозволу CORS перед «непростим» запитом | [CORS](../06_middleware_cache_jobs/cors.md#preflight) |
| **prompt injection** | текст з даних (новини), що намагається керувати моделлю як інструкція | [крок 7](../tutorials/07_llm_api/prompt_injection.md) |
| **`Protocol`** | інтерфейс для mypy за структурою: «має методи X» без спільного базового класу | [Анотації типів](../02_typing_and_pydantic/type_hints.md#protocol) |
| **Pydantic** | бібліотека перевірки й серіалізації даних за анотаціями типів | [Частина II](../02_typing_and_pydantic/README.md) |
| **rate limit** | обмеження кількості запитів за вікно часу; перевищення — `429` + `Retry-After` | [крок 4](../tutorials/04_middleware_redis/rate_limit.md) |
| **replay** | повторне надсилання перехопленого підписаного запиту; захист — час у підписі й журнал підписів | [крок 8](../tutorials/08_security/webhooks.md) |
| **Repository** | клас, у якому живуть усі запити до однієї таблиці; ендпоінт кличе його методи | [крок 3](../tutorials/03_sqlalchemy_alembic/repository.md) |
| **`response_model`** | модель, через яку FastAPI пропускає відповідь: зайві поля відкидаються | [Маршрути](../03_fastapi_core/routes_and_validation.md) |
| **REST** | стиль API: ресурси за адресами, стандартні методи й коди, без стану між запитами | [Принципи REST](../01_http_and_rest/rest_principles.md) |
| **`scope="function"`** | код після `yield` залежності виконується до відправлення відповіді | [Залежності](../03_fastapi_core/dependencies.md#yield-timing) |
| **`SecretStr`** | рядок, що друкується як `**********`; значення — `get_secret_value()` | [Налаштування](../02_typing_and_pydantic/settings.md#secret) |
| **smoke-тест** | короткий прогін головного шляху на справжньому стеку: «чи взагалі працює» | [крок 12](../tutorials/12_ci_cd/what_to_check.md) |
| **SSE** | Server-Sent Events: потік подій від сервера в одній HTTP-відповіді | [Стилі API](../01_http_and_rest/api_styles.md#sse) |
| **SSRF** | сервер на прохання клієнта звертається туди, куди не мав би: `localhost`, внутрішня мережа, метадані хмари | [крок 8](../tutorials/08_security/ssrf.md) |
| **Starlette** | ASGI-інструментарій, на якому побудовано FastAPI | [Що таке FastAPI](../03_fastapi_core/what_is_fastapi.md) |
| **`TestClient`** | клієнт HTTPX, що викликає застосунок без мережі; з `with` — запускає `lifespan` | [Шпаргалка FastAPI](fastapi_cheatsheet.md#testing) |
| **threadpool** | пул потоків (40), де FastAPI виконує `def`-ендпоінти й синхронні залежності | [Архітектура](architecture.md#endpoint-types) |
| **TTL** | час життя ключа в Redis; після нього ключ зникає сам | [крок 4](../tutorials/04_middleware_redis/cache.md) |
| **`TypedDict`** | словник з відомими ключами й типами — для mypy і Pydantic | [крок 1](../tutorials/01_typing_pydantic/type_hints_typeddict.md) |
| **Unit of Work** | усі зміни однієї операції — в одній транзакції: `COMMIT` разом або `ROLLBACK` разом | [Архітектура](architecture.md#uow) |
| **uvicorn** | ASGI-сервер, що запускає News Hub | [Команди](commands.md#run) |
| **WSGI** | синхронний інтерфейс сервер ↔ застосунок (Django без async, Flask) | [Архітектура](architecture.md#asgi-wsgi) |
| **WebSocket** | двобічне з'єднання поверх HTTP для повідомлень в обидва боки | [Стилі API](../01_http_and_rest/api_styles.md#websocket) |
| **`X-Forwarded-For`** | заголовок проксі з IP клієнта; вірити — лише своєму nginx (`FORWARDED_ALLOW_IPS`) | [крок 11](../tutorials/11_compose_deploy/nginx_real_ip.md) |

## А–Я { #cyrillic }

| Термін | Що це | Де |
|---|---|---|
| **валідатор** | функція Pydantic, що перевіряє або нормалізує поле чи модель | [Валідатори](../02_typing_and_pydantic/validators.md) |
| **версія кешу** | число в ключі кешу; запис збільшує його, і старі ключі більше не читаються | [крок 4](../tutorials/04_middleware_redis/cache.md) |
| **двійник Telegram** | локальний сервер з API Telegram (`tests/telegram_twin.py`) для тестів і розробки без мережі | [крок 9](../tutorials/09_telegram_bot/index.md) |
| **знімок новин** | збережені новини `data/rbc_news_snapshot.json`; `{"source": "snapshot"}` збирає з нього без мережі | [крок 2](../tutorials/02_fastapi_basics/scrape_endpoint.md) |
| **корутина** | функція `async def`, що може призупинитись на `await` і віддати потік іншим | [Архітектура](architecture.md#endpoint-types) |
| **межа довіри** | місце, де дані ззовні входять у код; тут їх перевіряють | [крок 1](../tutorials/01_typing_pydantic/trust_boundary.md) |
| **міграція** | версійований скрипт зміни схеми бази | [крок 3](../tutorials/03_sqlalchemy_alembic/alembic.md) |
| **мінімальні версії** | прогін тестів з найнижчими дозволеними версіями залежностей (`--resolution lowest-direct`) | [крок 5](../tutorials/05_api_testing/min_versions.md) |
| **образ / контейнер** | збірка файлів і налаштувань / запущений з неї процес | [крок 10](../tutorials/10_docker/index.md) |
| **пагінація** | видача колекції частинами: `skip`/`limit` або курсор | [Колекції](../01_http_and_rest/collections.md#pagination) |
| **патч там, де шукають** | `mock.patch("news_hub.scraper.parse_rbc_news")` — за модулем, що імпортував, а не що визначив | [крок 5](../tutorials/05_api_testing/mock_network.md) |
| **профіль Compose** | сервіс, що стартує лише з `--profile <ім'я>` (`polling`, `twin`) | [крок 11](../tutorials/11_compose_deploy/index.md) |
| **пул з'єднань** | набір відкритих з'єднань з базою, які запити беруть і повертають | [Архітектура](architecture.md#pool) |
| **сесія на запит** | одна сесія SQLAlchemy і одна транзакція на HTTP-запит (`get_db`) | [крок 3](../tutorials/03_sqlalchemy_alembic/session_per_request.md) |
| **том** | сховище Docker, що переживає контейнер (`pgdata`, `news_data`) | [крок 10](../tutorials/10_docker/user_data_env.md) |
| **фіксоване вікно** | rate limit: лічильник на ключ з TTL вікна (`INCR` + `EXPIRE NX`) | [крок 4](../tutorials/04_middleware_redis/rate_limit.md) |
| **шар образу** | результат однієї інструкції `Dockerfile`; незмінені шари беруться з кешу | [крок 10](../tutorials/10_docker/layers_cache.md) |
