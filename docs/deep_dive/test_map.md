# Карта тестів

> News Hub Deep Dive · сторінка 5 з 6. Код: [`steps/12_ci_cd/tests/`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/12_ci_cd/tests),
> [`pytest.ini`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/pytest.ini),
> [`.github/workflows/news_hub.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/news_hub.yml).
> Теорія: [Частина VII. Тестування API](../07_testing/README.md), [крок 5](../tutorials/05_api_testing/index.md).

## Задача { #task }

371 тест у 28 файлах — забагато, щоб тримати в голові. Ця сторінка відповідає на три питання:

1. **Що в тестах справжнє, а що підмінене** — і чого тому тести не бачать.
2. **Що ловить кожен файл** і які модулі він покриває.
3. **Де тести запускаються** — локально і в кожному job CI.

## Цифри { #numbers }

Усе — з запусків на фінальному коді (час — на одному ноутбуці, у CI інший):

| Команда | Результат |
|---|---|
| `pytest --collect-only -m ""` | 371 тест: unit 212, integration 151, docker 6, live 2 |
| `pytest -q` | `363 passed, 8 deselected in 19.33s` |
| `pytest -m unit -q` | `212 passed, 159 deselected in 6.57s` |
| `pytest -m integration -q` | `151 passed, 220 deselected in 18.44s` |
| `TEST_DATABASE_URL=postgresql+asyncpg://… TEST_REDIS_URL=redis://…/15 pytest -q` | `363 passed, 8 deselected` за 34–36 с (PostgreSQL 16, Redis 7) |
| `pytest -m docker -q` | `6 passed, 365 deselected in 26.27s` |
| `mypy --strict news_hub` | `Success: no issues found in 26 source files` |
| `pytest -m llm` | не запускалось: потрібен ключ і мережа, витрачає квоту |

`8 deselected` у звичайному запуску — це 6 тестів образу і 2 справжні виклики LLM: `pytest.ini` вимикає їх
за замовчуванням (`addopts = -m "not llm and not docker"`).

## Як тести поділено { #layers }

Маркер ставить **папка**, а не декоратор у кожному файлі — `tests/conftest.py`:

```python title="tests/conftest.py (фрагмент)"
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Маркер з назви папки: не треба пам'ятати про @pytest.mark.unit у кожному файлі."""
    for item in items:
        for layer in ("unit", "integration", "docker"):
            if f"{Path('tests') / layer}" in str(item.path):
                item.add_marker(getattr(pytest.mark, layer))
```

Маркер `llm` тести `tests/live/` ставлять собі самі. Як це з'явилось — [крок 5](../tutorials/05_api_testing/test_layers.md).

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    U["unit · 212<br>функція чи клас"] --> I["integration · 151<br>API + база + Redis"]
    I --> D["docker · 6<br>образ і контейнер"]
    I --> L["live · 2<br>справжня модель"]
    CI["CI: smoke.sh<br>увесь стек через nginx"] -.-> D

    class U success
    class I step
    class D,CI decision
    class L warning
```

### Що справжнє, а що підмінене { #what-is-real }

| Шар | Справжнє | Підмінене | Чого тому не бачить |
|---|---|---|---|
| `unit` | код однієї функції чи класу; `fakeredis` у тестах breaker і кешу | мережа (мок `session.get`), база, `FakeLLM`, сторінки — HTML-фікстури | SQL, порядок middleware, `Depends` |
| `integration` | застосунок FastAPI цілком: middleware, `Depends`, `lifespan`, SQL на SQLite (або PostgreSQL), aiohttp проти локальних серверів, aiogram проти двійника | база — SQLite у пам'яті з `create_all`, Redis — fakeredis, LLM — `FakeLLM`, Telegram — двійник, rbc.ua — `fake_scraper` | міграції, nginx, образ, справжні провайдери |
| `docker` | `docker build`, `docker run`, `docker stop`, `alembic upgrade head` на томі | нічого не підмінено, але без PostgreSQL і nginx | Compose, мережі, nginx |
| `live` | справжній Gemini (або Anthropic) | — | — (за це й платимо) |
| CI `smoke.sh` | увесь стек Compose через nginx: PostgreSQL, Redis, `migrate`, `api`, `nginx` | `.env` з випадковими секретами | Telegram, LLM |

Головна межа: **тести не застосовують міграцій** — тестову базу створює `Base.metadata.create_all`
([Модель даних](data_model.md#migrations)). Міграції ловлять `alembic check` у CI, `test_migrations_run_on_a_volume`
і `migrate` у smoke-тесті.

## Фікстури і двійники { #fixtures }

`tests/integration/conftest.py` — серце інтеграційних тестів. Він ставить змінні середовища **до** імпорту
застосунку (`REDIS_URL`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH` з 4 раундами bcrypt замість 12, `WEBHOOK_SECRET`) і
підміняє три залежності (`TestDatabase.install`):

| Фікстура | Що дає | Що підміняє |
|---|---|---|
| `html` (`tests/conftest.py`) | `html("demo_newsline")` → вміст `tests/fixtures/demo_newsline.html` | мережу для парсера |
| `anon` | `TestClient` **без** токена — «будь-хто в інтернеті» | `get_db` → тестова база, `get_session_factory` → та сама база для фонових задач, `get_scrapers` → `fake_scraper`; `app.state.llm = FakeLLM()`; `flushdb` |
| `client` | той самий `TestClient`, але з `Authorization: Bearer <токен адміна>` | — |
| `aclient` | `httpx.AsyncClient` + `ASGITransport`, адмін; `lifespan` запускається вручну | те саме, що `anon` |
| `fake_llm` | `FakeLLM` зі сценарієм: `fake_llm.replies.extend([...])`, промпти — `fake_llm.calls` | `get_llm_client` |
| `twin` | двійник Telegram Bot API на `127.0.0.1` | api.telegram.org |
| `telegram` | `BotHarness`: бот і диспетчер над тестовою базою; `say("/news")` → що бот відповів | — |
| `bot_api` | `aclient` з увімкненим ботом на двійнику — як після `lifespan` з `BOT_TOKEN` і webhook | `app.state.bot`, `dispatcher`, `telegram` |

### Двійники замість моків { #doubles }

| Двійник | Де | Що відтворює | Що ловить, чого не зловив би мок |
|---|---|---|---|
| `FakeLLM` | `news_hub/llm.py:196` | сценарій відповідей і винятків, `demo_reply` з заголовка | скільки разів і з яким промптом викликали модель (`test_analysis.py::test_injection_does_not_change_instructions`) |
| двійник Telegram | `tests/telegram_twin.py` | формат Bot API, `401`, `403 bot was blocked`, `429 retry_after`, правила HTML, 4096 символів, доставка webhook із секретним заголовком | невалідний HTML у відповіді бота (`test_bot_formatting.py::test_twin_follows_html_rules`), розріз посеред тегу (`test_old_split_cuts_inside_markup`) |
| локальний aiohttp-сервер | `tests/integration/test_scraper_server.py` | справжні з'єднання, статуси, тайм-аути, байти | сторінка з одним битим байтом UTF-8 валила весь збір (`test_undecodable_page_does_not_kill_scrape`) — мок `text()` декодування не робить |
| локальний RSS-сервер + `FetchPolicy` | `tests/integration/test_sources_ssrf.py` | перенаправлення, типи вмісту, розмір | перенаправлення на внутрішню адресу перевіряється знову (`test_redirect_is_checked_again`) |
| fakeredis | `REDIS_URL=fakeredis://` | команди Redis у пам'яті процесу | — але **не** гонки: fakeredis не віддає керування циклу подій |

Межа fakeredis задокументована в самому тесті: `test_async_api.py::test_concurrent_requests_hit_rate_limit_exactly`
шле 10 запитів одночасно і чекає рівно 5 × `422` + 5 × `429`. «Наївний» лічильник (`GET`, потім `SET`) на
fakeredis теж пройде — ловить його лише справжній Redis (`TEST_REDIS_URL`).

## Що ловить кожен файл { #files }

Кількість — з `pytest --collect-only` (параметризовані тести рахуються окремо). Крок — де файл з'явився.

### `tests/unit/` — 212 { #unit }

| Файл | Тестів | Крок | Що ловить |
|---|---|---|---|
| `test_parser.py` | 9 | 5 | дві стратегії `parse_rbc_news` (контейнери, посилання), справжня розмітка rbc.ua, що парсер пропускає |
| `test_models.py` | 22 | 5 | `NewsItem`: поля з URL, формати часу, недопустимі значення, `is_rbc_host` (`fakerbc.ua`), `frozen`, знімок валідний |
| `test_pipeline.py` | 2 | 5 | конвеєр «парсер → модель» на обох фікстурах: кожна розібрана новина проходить `NewsItem` |
| `test_scraper.py` | 6 | 5 | `fetch_one` під моком: мережеві помилки → помилка сторінки, злиття сторінок без дублікатів, `patch` там, де використовується |
| `test_pravda.py` | 18 | 6 | специфікація для AI: RSS у порядку стрічки, чисті поля, київський час, без мережі, межові домени (`allowed_hosts` × 11) |
| `test_pravda_review.py` | 3 | 6 | що знайшла рецензія коду AI: категорія «2026», порожній `pubDate`, база поясів у Windows |
| `test_llm.py` | 25 | 7 | пул Gemini (наступна модель, 4xx — одразу стоп, мережа), Anthropic, `FakeLLM`, breaker (поріг, закриття, одночасні збої, без Redis), `make_llm` з env |
| `test_analysis.py` | 20 | 7 | `NewsAnalysis`, один повтор (× 7 невалідних відповідей), токени обох спроб, ін'єкція в заголовку, кеш і `PROMPT_VERSION` |
| `test_security.py` | 24 | 8 | bcrypt (сіль, > 72 байт), токен туди-назад, прострочений, підроблені (× 7), налаштування з env, обрізаний хеш при старті, `LoginGuard` (лічильник на ім'я, скидання після успіху), адміни Telegram у `AdminSettings` і помилка старту для поганого `BOT_ADMIN_IDS` (× 3) |
| `test_safe_fetch.py` | 35 | 8 | `is_public_ip` (× 16), небезпечні URL (× 14), IPv4 всередині IPv6, явна `FetchPolicy` |
| `test_webhooks.py` | 15 | 8 | підпис HMAC повертає id доставки, відхилені (× 11: змінене тіло, старий, змінений id доставки, немає id, `../../etc/passwd` як id…), `claim_delivery` — та сама доставка приймається один раз, переслана з новим часом зберігає id, секрет Telegram |
| `test_bot_formatting.py` | 33 | 9 | `esc`, `link`, `split_message`, `normalize_keyword` (× 9), `matches` (× 6), правила HTML двійника (× 8), `BotSettings` (без адмінів — вони в `AdminSettings`) |

### `tests/integration/` — 151 { #integration }

| Файл | Тестів | Крок | Що ловить |
|---|---|---|---|
| `test_api.py` | 17 | 5 | список і фільтри (× 4), `422` (× 5), збір знімка, повторний збір нічого не додає, OpenAPI |
| `test_crud.py` | 9 | 5 | `201` з полями з URL, `409` на той самий url, `PATCH` лише переданих полів, пошук без регістру й буквальний, `GROUP BY`, **невдалий COMMIT — `500`, а не `200`** |
| `test_db.py` | 4 | 5 | **справжній** `get_db` (не копія з conftest): COMMIT, ROLLBACK; гілка PostgreSQL у `make_engine` |
| `test_redis.py` | 9 | 5 | `X-Request-ID`, MISS → HIT, запис скидає кеш, `409` не скидає, `429` з `Retry-After`, ключ ліміту без TTL «лікується», фонова задача done / failed |
| `test_async_api.py` | 3 | 5 | той самий API через `httpx.AsyncClient`, одночасні запити й rate limit |
| `test_scraper_server.py` | 5 | 5 | справжній aiohttp проти локального сервера: `gather` паралельний, черга — ні, `403`, тайм-аут, битий байт |
| `test_analyze_api.py` | 16 | 7 | аналіз через API: `db` / `cache` / `llm`, `force`, `502`, `503` без ключа, breaker `503` з `Retry-After`, пакетна задача, ліміт аналізу |
| `test_admin_api.py` | 36 | 8 | **кожен** маршрут поза `PUBLIC` вимагає адміна; анонім → `401` (× 14), `403`, прострочений і непідписаний токен, перебір пароля з адреси → `429`, невдачі на ім'я з будь-яких адрес → `429` (`LoginGuard`), токен з `Cache-Control: no-store`, заголовки безпеки на кожній відповіді (на `/docs` — без CSP), `DOCS_ENABLED` (× 7), `503` без налаштувань |
| `test_sources_ssrf.py` | 14 | 8 | RSS-джерела: небезпечні адреси не зберігаються (× 5), перенаправлення перевіряються знову (× 3), не RSS → `502` (× 3), імена, що резолвляться всередину |
| `test_webhooks_api.py` | 9 | 8 | підписаний webhook без JWT, відхилені (× 4), точний повтор → `200` з тим самим `job_id`, переслана доставка з новим підписом не запускає збір удруге, підпис перевіряється **до** JSON |
| `test_bot.py` | 11 | 9 | команди через двійника: `/news`, `/digest` з LLM і без, підписки і ліміт, `/scrape` лише адміну і з тим самим лімітом збору, що й API, екранування імені, rate limit відповідає один раз |
| `test_notify.py` | 6 | 9 | нові новини — підписникам один раз, `403` → підписки видалено, `429` → повтор, багато збігів — кілька валідних повідомлень |
| `test_telegram_webhook.py` | 9 | 9 | `lifespan` ставить webhook і не видаляє його, неправильний секрет `401` (× 3), не update `400`, **API стартує, коли Telegram лежить** |
| `test_health.py` | 3 | 10 | `/health/ready`: база й Redis відповідають; база впала → `503`, але процес живий; Redis упав → `503` |

### `tests/docker/` і `tests/live/` { #docker-live }

| Файл | Тестів | Крок | Що ловить |
|---|---|---|---|
| `docker/test_image.py` | 6 | 10 | в образі немає `.env`, `.venv`, бази, кешу; немає dev-залежностей; користувач не root і не може змінити код; healthcheck `healthy`; `docker stop` — коректна зупинка; міграції на томі |
| `live/test_llm_live.py` | 2 | 7 | справжня модель приймає формат запиту і повертає валідний `NewsAnalysis` |

## Модуль → тести { #modules }

Які тести покривають кожен модуль. «Прямо» — тест імпортує модуль (з `ast`, як граф на сторінці
[Архітектура](architecture.md#imports)); «через API» — модуль працює всередині запиту `TestClient`.

| Модуль | Прямо | Через API чи бота |
|---|---|---|
| `parser.py` | `test_parser`, `test_pipeline`, `factories.py` | `test_api` (знімок) |
| `models.py` | `test_models`, `test_pipeline`, `test_pravda`, `test_pravda_review`, `test_analysis`, `test_bot` | `test_api`, `test_crud` |
| `rss.py` | `test_pravda`, `test_pravda_review`, `test_sources_ssrf` | `test_sources_ssrf` |
| `snapshot.py` | `test_models`, `test_analysis`, `test_bot`, `test_llm_live` | `test_api`, `test_notify` |
| `scraper.py` | `test_scraper` (мок), `test_scraper_server` (сервер), `test_api`, `test_redis` | — (у API підмінений `fake_scraper`) |
| `db.py` | `test_db`, `test_crud`, `test_health` | усі інтеграційні |
| `tables.py`, `repository.py` | `test_db`, `test_bot`, `test_notify`, `test_bot_formatting` | усі інтеграційні |
| `cache.py`, `middleware.py` | `test_redis`, `test_async_api`, `test_analyze_api`, `test_health`, `test_admin_api` (`LIMITS`), `test_bot` (`LIMITS`) | усі інтеграційні |
| `jobs.py` | — | `test_redis`, `test_analyze_api`, `test_notify`, `test_webhooks_api` |
| `llm.py`, `analysis.py` | `test_llm`, `test_analysis`, `test_analyze_api`, `test_llm_live` | `test_bot` (`/digest`) |
| `security.py` | `test_security`, `test_admin_api` | усі, де `client` (токен адміна); `test_bot` (адміни Telegram) |
| `safe_fetch.py` | `test_safe_fetch`, `test_sources_ssrf` | `test_sources_ssrf` |
| `webhooks.py` | `test_webhooks`, `test_webhooks_api` | `test_telegram_webhook` |
| `notify.py` | `test_bot_formatting`, `test_notify` | `test_bot` (`/scrape`) |
| `bot/*` | `test_bot_formatting`, `test_bot` (через `create_dispatcher`) | `test_telegram_webhook`, `test_notify` |
| `api.py` | майже всі інтеграційні (`from news_hub.api import app`) | — |
| `bot/__main__.py` | — | — (polling перевіряється вручну на двійнику) |

`bot/__main__.py` — єдиний модуль без жодного тесту: він лише збирає те, що тестується окремо
(`create_bot`, `create_dispatcher`, `make_redis`, `make_llm`, `load_admin_settings`), і викликає `dp.start_polling`.

## Тести, які ловлять те, чого не видно { #notable }

Кілька тестів варто знати на ім'я — кожен з'явився після справжньої помилки або щоб її не допустити:

| Тест | Що ловить |
|---|---|
| `test_crud.py::test_failed_commit_is_500_not_200` | без `scope="function"` COMMIT ішов би **після** відповіді — клієнт отримав би `200`, а даних немає |
| `test_admin_api.py::test_every_other_endpoint_requires_admin` | обходить усі маршрути `app.routes`; новий ендпоінт без `AdminDep` і без запису в `PUBLIC` — червоний тест |
| `test_redis.py::test_rate_limit_key_without_ttl_heals` | ключ ліміту без TTL (процес упав між `INCR` і `EXPIRE`) не блокує клієнта назавжди |
| `test_redis.py::test_failed_write_keeps_cache` | `409` не скидає кеш |
| `test_async_api.py::test_concurrent_requests_hit_rate_limit_exactly` | гонка лічильника — лише на справжньому Redis |
| `test_security.py::test_truncated_hash_fails_at_startup` | обрізаний `$2b$12` з `.env` без лапок — помилка при старті, а не `500` на вході |
| `test_telegram_webhook.py::test_api_starts_while_telegram_is_down` | недоступний Telegram не зупиняє старт API (крок 11) |
| `test_scraper_server.py::test_undecodable_page_does_not_kill_scrape` | один битий байт UTF-8 не губить новини решти сторінок |
| `test_bot_formatting.py::test_old_split_cuts_inside_markup` | старе розбиття «кожні N символів» різало `<b>…</b>` навпіл — Telegram відхилив би обидві частини |
| `test_pravda_review.py::test_item_without_category_is_not_named_after_year` | код AI брав другий сегмент URL і для pravda.com.ua → категорія «2026» |
| `test_admin_api.py::test_login_lockout_counts_failures_per_name_from_any_address` | ліміт на адресу не бачить підбору з тисячі адрес — тест знімає його (`LIMITS["login"]`) і перевіряє, що 20 невдач на ім'я закривають вхід навіть з правильним паролем, а інше ім'я — ні |
| `test_webhooks_api.py::test_resent_delivery_with_new_signature_does_not_scrape_twice` | старий захист (ключ — підпис) пропускав повтор з новим часом: збір запускався двічі |

## Ті самі тести на справжніх серверах { #real-servers }

Інтеграційні тести вміють працювати і з SQLite + fakeredis, і з PostgreSQL + Redis — адреси беруться з
`TEST_DATABASE_URL` і `TEST_REDIS_URL`:

```bash
docker run -d --rm --name pg -e POSTGRES_DB=news_hub_test -e POSTGRES_USER=news -e POSTGRES_PASSWORD=news \
    -p 127.0.0.1:5432:5432 postgres:16-alpine
docker run -d --rm --name redis -p 127.0.0.1:6379:6379 redis:7-alpine
export TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test
export TEST_REDIS_URL=redis://localhost:6379/15            # база 15 очищується перед кожним тестом
DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head && DATABASE_URL=$TEST_DATABASE_URL alembic check
pytest -q
```

Так і працює job `postgres` у CI. Локально (на інших портах) це дало `No new upgrade operations detected.` і
`363 passed, 8 deselected` — у трьох прогонах поспіль.

!!! warning "Якщо тест з токеном адміна зрідка падає з `401 недійсний токен`"
    Під час першої перевірки цієї сторінки три з чотирнадцяти прогонів на PostgreSQL упали — щоразу один тест і щоразу
    інший. У прогоні, де збережено подробиці, — запит з токеном адміна отримав `{'detail': 'недійсний токен'}`
    (`test_notify.py::test_background_job_notifies_too`), а окремо кожен тест проходить. Причина — не код, а годинник машини: під
    WSL2 системний час за чотири хвилини вісім разів відскочив приблизно на 95 с назад і повернувся. PyJWT
    відхиляє токен, у якого `iat` (час видачі) у майбутньому: `ImmatureSignatureError` — підклас
    `InvalidTokenError`, а `require_admin` (`security.py:206`) відповідає на нього `401 недійсний токен`.
    Перевірити годинник: порівняти `time.time()` з `time.monotonic()` у циклі. На серверах з NTP таких
    стрибків зазвичай немає; якщо годинники кількох машин розходяться, `jwt.decode` має параметр `leeway`.

## CI: які тести де запускаються { #ci }

`.github/workflows/news_hub.yml` запускається на кожен PR, що змінює `steps/12_ci_cd/**`, сам workflow або
`.gitleaks.toml`, і на push у `main`. Сім jobs:

```mermaid
flowchart LR
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    T["tests<br>Python 3.10 · 3.13"] --> D["docker<br>образ + smoke"]
    T --> P["publish<br>ghcr.io"]
    M["min-versions<br>uv lowest-direct"] --> P
    PG["postgres<br>Alembic + PostgreSQL"] --> P
    TY["types<br>mypy --strict"] --> P
    SC["supply-chain<br>lock · pip-audit · gitleaks"] --> P
    D --> P
    P --> MAIN{"push у main?"}
    MAIN -->|"так"| IMG["образ<br>sha + latest"]
    MAIN -->|"ні"| SKIP["пропущено<br>PR"]

    class T,M,PG,TY,SC step
    class D decision
    class P success
    class MAIN decision
    class IMG success
    class SKIP warning
```

| Job | Що запускає | Які тести | Що ловить, чого не ловлять інші |
|---|---|---|---|
| `tests` (матриця 3.10, 3.13) | `pytest -m unit -q`, потім `pytest -q` | 212, потім 363 | синтаксис і поведінка на найстарішому й найновішому Python |
| `min-versions` | `uv pip install --resolution lowest-direct -r requirements-dev.txt`, `pytest -q` | 363 | нижні межі в `requirements.txt` неправдиві (так у кроці 5 знайшлась вада `parser.py` з `beautifulsoup4 4.12`) |
| `postgres` | `alembic upgrade head`, `alembic check`, `pytest -q` з `TEST_DATABASE_URL` / `TEST_REDIS_URL` | 363 | міграції, SQL PostgreSQL, гонки на справжньому Redis |
| `types` | `mypy --strict news_hub` | — | типи |
| `supply-chain` («залежності й секрети») | `uv pip compile … --generate-hashes` + `git diff --exit-code -- requirements.lock`; `uvx pip-audit==2.10.1 -r requirements.lock --require-hashes`; gitleaks v8.30.1 (у Docker) по **всій** історії git (`fetch-depth: 0`) з `.gitleaks.toml` | — | `requirements.lock` розійшовся з `requirements.txt`; відома вразливість у будь-якому з 70 пакетів образу; секрет у будь-якому коміті — навіть видалений наступним |
| `docker` (`needs: tests`) | `pytest -m docker -q`, `scripts/make_env.py`, `scripts/smoke.sh` | 6 + smoke | образ, Compose, nginx, `migrate`, порти назовні |
| `publish` (`needs:` усі шість, лише push у `main`) | `docker/build-push-action` → `ghcr.io/<власник>/<репозиторій>/news_hub` | — | — |

`smoke.sh` — ще 10 перевірок поверх тестів: готовність через nginx, `/nginx-health`, вхід адміна, запис без токена
→ `401`, збір знімка → `news_saved: 168`, `{"count":168}` у PostgreSQL, `/docs` → `404` (`DOCS_ENABLED=false`),
`X-Content-Type-Options: nosniff` через nginx, `Server: nginx` без версії, база й Redis без портів назовні.

Що job `supply-chain` показав на фінальному коді (локально, тими самими командами):

```text
$ uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock
$ cmp requirements.lock <копія до перегенерації>      # без виводу: lock не змінився
$ uvx pip-audit==2.10.1 -r requirements.lock --require-hashes --disable-pip --progress-spinner off
No known vulnerabilities found
$ docker run … ghcr.io/gitleaks/gitleaks:v8.30.1 git /repo --config /repo/.gitleaks.toml --redact --no-banner
INF 25 commits scanned.
INF no leaks found
```

`.gitleaks.toml` — правила gitleaks за замовчуванням плюс винятки для чотирьох навчальних значень (тестовий JWT
з `alg: none`, демонстраційний JWT, одноразовий `JWT_SECRET` з прикладу, явно підроблений секрет налаштувань).
Кожен виняток — конкретне значення, а не ціла папка: справжній секрет у `tests/` чи `docs/` gitleaks знайде.
Чому jobs саме такі й у такому порядку — [крок 12](../tutorials/12_ci_cd/what_to_check.md),
[порядок і паралельність](../tutorials/12_ci_cd/order_and_parallel.md).

## Що далі { #next }

[Як розширювати](extending.md) — які з цих тестів зачепить твоя зміна і які треба дописати.
