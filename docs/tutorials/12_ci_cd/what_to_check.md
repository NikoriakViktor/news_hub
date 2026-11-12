# Що саме перевіряти

> Крок 12 · розділ 2 з 4. Код: [`.github/workflows/news_hub.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/news_hub.yml) (jobs `tests`, `min-versions`, `postgres`, `types`, `supply-chain`, `docker`), [`scripts/smoke.sh`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/scripts/smoke.sh), [`requirements.txt`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/requirements.txt), [`requirements.lock`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/requirements.lock), [`.gitleaks.toml`](https://github.com/NikoriakViktor/news_hub/blob/main/.gitleaks.toml).
> Теорія: [Частина VII. Тестування API](../../07_testing/README.md), [Частина X. Docker, Compose і CI/CD](../../10_docker_and_ci/README.md).

## Задача { #task }

Локально `pytest -q` проходить: 363 тести на SQLite у пам'яті й fakeredis, на тому Python і тих версіях пакетів, що стоять у тебе. Але `news_hub` обіцяє більше:

- `CLAUDE.md` кроку: «Python 3.10+»;
- `requirements.txt`: `fastapi>=0.121`, `pydantic>=2.9`, `sqlalchemy[asyncio]>=2.0.30`… — «працює з цими версіями й новішими»;
- у продакшні — PostgreSQL і справжній Redis, схема бази — з міграцій Alembic, а не з `create_all`;
- в образі — саме ті пакети, які перевірили, без відомих вразливостей; у git — жодного справжнього секрету, навіть у старих комітах;
- користувач бачить не функції, а зібраний образ за nginx.

Кожну обіцянку має перевіряти окремий job.

## Тести без списку { #test-list }

Workflow Django-книги ([розділ 1](triggers.md#start)) перелічує модулі тестів руками: `manage.py test notes_app.tests.test_models notes_app.tests.test_services …`. Новий файл тестів не потрапить у CI, поки хтось не згадає дописати його в список, — і CI мовчки його не запускатиме. А `coverage run manage.py test …` одразу після цього — **другий** повний прогін тих самих тестів: удвічі довше, нового знання не дає.

У `news_hub.yml` тести знаходить сам pytest (`testpaths = tests` у `pytest.ini`), списку немає:

```yaml title="news_hub.yml → job tests"
      - run: pip install -r requirements-dev.txt
      - run: pytest -m unit -q        # швидкі — першими: падають за секунди
      - run: pytest -q                # усі: SQLite у пам'яті + fakeredis + двійник Telegram + FakeLLM
```

Тут unit-тести справді йдуть двічі, але свідомо: 212 швидких тестів (у локальному запуску — 7–9 с) падають раніше, ніж стартують інтеграційні, і перша причина видна в журналі одразу. Покриття, коли потрібне, — одним прогоном (`pytest --cov=news_hub`), а не окремим повторним.

## Карта jobs { #jobs }

| Job (назва в PR) | Що робить | Що ловить |
|---|---|---|
| `pytest · Python 3.10` / `pytest · Python 3.13` (matrix) | `pytest -m unit`, потім `pytest` | код, що працює лише на новому (або лише на старому) Python, і пакети, що для різних Python ставляться різних версій |
| `pytest · мінімальні версії (Python 3.10)` | `uv pip install --resolution lowest-direct`, `pytest` | неправдиві нижні межі в `requirements.txt` |
| `pytest і Alembic · PostgreSQL 16 + Redis 7` | `alembic upgrade head`, `alembic check`, `pytest` | відмінності SQLite і PostgreSQL, fakeredis і Redis; змінену модель без міграції |
| `mypy --strict` | `mypy --strict news_hub` | помилки типів |
| `залежності й секрети` (`supply-chain`) | lock відповідає `requirements.txt`; `pip-audit` по lock; gitleaks по всій історії git | застарілий lock, пакет з відомою вразливістю, секрет у коміті ([нижче](#supply-chain)) |
| `образ і smoke-тест Compose` | `pytest -m docker`, `make_env.py`, `smoke.sh` | зібрана система не працює: образ (крок 10) і стек через nginx (крок 11) |
| `публікація образу в ghcr.io` | лише push у `main` | — (це CD, [розділ 4](permissions_and_publish.md#publish)) |

## Дві версії Python { #matrix }

```yaml title="news_hub.yml → job tests"
    strategy:
      fail-fast: false               # впала 3.10 — все одно дізнатися, що з 3.13
      matrix:
        python: ["3.10", "3.13"]
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: ${{ matrix.python }}
          cache: pip
          cache-dependency-path: ${{ env.PROJECT }}/requirements*.txt
```

Один job — два запуски: `3.10` — найстаріша версія, яку обіцяє проєкт, `3.13` — найновіша. Образ працює на третій, `python:3.12-slim` (`Dockerfile`), і його перевіряє окремий job `docker`.

Matrix перевіряє не лише синтаксис мови. Той самий `pip install -r requirements-dev.txt` на різних Python ставить **різні** пакети. Локальний запуск 2026-11-12 (через `uv`, як нижче):

| | Python 3.10.19 | Python 3.13.17 |
|---|---|---|
| `sqlalchemy` | 2.0.57 | 2.1.8 |
| `fastapi`, `pydantic`, `aiogram` | 0.162.5, 2.13.5, 3.31.0 | 0.162.5, 2.13.5, 3.31.0 |
| `pytest -m unit -q` | 212 passed, 159 deselected | 212 passed, 159 deselected |
| `pytest -q` | 363 passed, 8 deselected | 363 passed, 8 deselected |

SQLAlchemy 2.1 вимагає Python ≥ 3.11 (`Requires-Python: >=3.11`), тож на 3.10 лишається гілка 2.0. Якби код використав щось, чого немає в 2.0, — червоною стала б лише 3.10.

## Мінімальні версії { #min-versions }

`requirements.txt` обіцяє `fastapi>=0.121` — «працює з 0.121 і новішими». Але CI, як і ти, ставить **найновіші** версії, тож нижню межу ніхто ніколи не перевіряє. Вона правдива в день, коли її записали, а потім код починає користуватися новішим API — і межа тихо бреше.

[`uv`](https://docs.astral.sh/uv/) уміє поставити саме найменші дозволені версії:

```yaml title="news_hub.yml → job min-versions"
  min-versions:
    name: pytest · мінімальні версії (Python 3.10)
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v6
      # lowest-direct: кожна залежність з requirements.txt — найменша дозволена версія (>=…).
      # Так перевіряється, що нижні межі в requirements.txt правдиві, а не лише «зараз працює з найновішими».
      - run: uv venv --python 3.10 .venv
      - run: uv pip install --resolution lowest-direct -r requirements-dev.txt
      - run: .venv/bin/pytest -q
```

`lowest-direct` — найменші версії **прямих** залежностей (тих, що в `requirements*.txt`); їхні власні залежності — найновіші сумісні. Python — теж найстаріший, 3.10.

### Результат: межі правдиві { #min-versions-result }

Ті самі команди локально:

```text
$ uv venv --python 3.10 .venv
$ uv pip install --resolution lowest-direct -r requirements-dev.txt
 + aiogram==3.15.0
 + aiohttp==3.10.10
 + alembic==1.13.0
 + anthropic==1.0.0
 + bcrypt==4.0.0
 + fakeredis==2.26.0
 + fastapi==0.121.0
 + google-genai==1.39.0
 + httpx==0.28.1
 + mypy==1.10.0
 + pydantic==2.9.0
 + pyjwt==2.4.0
 + pytest==8.2.0
 + redis==5.0.1
 + sqlalchemy==2.0.30
 + starlette==0.49.3
 + uvicorn==0.30.0
$ .venv/bin/pytest -q
363 passed, 8 deselected, 30 warnings in 17.70s
```

(Вибрано рядки прямих залежностей; `pytest` — 8.2.0, а не 8.0: такої вимагає `pytest-asyncio` 0.24. 30 попереджень у `tests/integration/test_admin_api.py` — ``PydanticDeprecatedSince20: The `__fields__` attribute is deprecated``: старіші бібліотеки звертаються до застарілого API Pydantic; тести це не валить.)

### Результат: межа бреше { #min-versions-broken }

Чи ловить job справжню проблему? Знизимо в копії кроку межу FastAPI до `fastapi>=0.115` — на вигляд безпечно, «у нас же нічого особливого»:

```text
$ uv pip install --resolution lowest-direct -r requirements-dev.txt
 + fastapi==0.115.0
 + starlette==0.38.6
$ .venv/bin/pytest -q
tests/integration/conftest.py:33: in <module>
    from news_hub.api import app, get_llm_client, get_scrapers, get_session_factory
news_hub/api.py:201: in <module>
    SessionDep = Annotated[AsyncSession, Depends(get_db, scope="function")]
E   TypeError: Depends() got an unexpected keyword argument 'scope'
=========================== short test summary info ============================
ERROR tests/integration - TypeError: Depends() got an unexpected keyword argu...
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
8 deselected, 1 error in 4.50s
```

`Depends(..., scope="function")` з'явився у FastAPI 0.121 — про це й коментар біля межі в `requirements.txt`. Звичайні jobs із `>=0.115` лишилися б зеленими: вони ставлять найновішу FastAPI. Червоним став би лише `min-versions`. Тому в `CLAUDE.md` кроку правило: «Нижня межа в `requirements.txt` — справжня: CI ставить саме її. Підняв API залежності — підніми межу».

## PostgreSQL і Redis у `services` { #postgres }

Тести за замовчуванням — на SQLite у пам'яті й fakeredis: швидко, без серверів. Але продакшн — PostgreSQL і Redis, і різниця реальна: типи й обмеження бази, транзакції, а fakeredis не віддає керування циклу подій — одночасних запитів на ньому не буває, тож гонку в rate limit він не покаже (`tests/integration/test_async_api.py`). Тому один job піднімає справжні сервери:

```yaml title="news_hub.yml → job postgres"
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: news_hub_test
          POSTGRES_USER: news
          POSTGRES_PASSWORD: news         # одноразова база CI, живе хвилини; не секрет
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql+asyncpg://news:news@localhost:5432/news_hub_test
      TEST_REDIS_URL: redis://localhost:6379/15
      DATABASE_URL: postgresql+asyncpg://news:news@localhost:5432/news_hub_test
```

- `options: --health-cmd …` — GitHub чекає, поки контейнер стане `healthy`, і лише тоді починає кроки job. Без цього перший тест міг би постукати в базу, яка ще стартує.
- `TEST_DATABASE_URL` і `TEST_REDIS_URL` читає `tests/integration/conftest.py` (крок 5): без них — SQLite і fakeredis. Redis-база 15 очищується перед кожним тестом.
- `DATABASE_URL` — для Alembic: `migrations/env.py` бере адресу з `news_hub.db.DATABASE_URL` (крок 3).

### `alembic check`: модель без міграції { #alembic-check }

```yaml
      - name: міграції на чистій базі й перевірка, що моделі збігаються з міграціями
        run: |
          alembic upgrade head
          alembic check
      - run: pytest -q
```

`alembic upgrade head` на чистій базі перевіряє, що всі міграції 0001–0004 проходять по черзі. `alembic check` порівнює схему після міграцій з моделями в `tables.py`: якщо в моделі є те, чого міграції не створюють, — помилка.

Локально з PostgreSQL 16 і Redis 7 у контейнерах:

```text
$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, news table — таблиця новин агрегатора (крок 3)
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, llm analysis — колонки аналізу LLM у таблиці news (крок 7)
INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003, sources — RSS-джерела, які додає адмін (крок 8)
INFO  [alembic.runtime.migration] Running upgrade 0003 -> 0004, subscriptions — підписки чатів Telegram на ключові слова (крок 9)
$ alembic check
No new upgrade operations detected.
$ pytest -q
363 passed, 8 deselected in 35.17s
```

А тепер «забули міграцію»: у копії кроку додаємо в `NewsRow` колонку й не пишемо міграції.

```python title="news_hub/tables.py (зміна в копії)"
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author: Mapped[str | None] = mapped_column(String(100))      # нова колонка, міграції немає
```

```text
$ pytest -q                                   # SQLite у пам'яті, як за замовчуванням
363 passed, 8 deselected in 17.83s
$ alembic upgrade head && alembic check       # чиста PostgreSQL 16
INFO  [alembic.autogenerate.compare.tables] Detected added column 'news.author'
ERROR [alembic.util.messaging] New upgrade operations detected: [('add_column', None, 'news', Column('author', String(length=100), table=<news>))]
FAILED: New upgrade operations detected: [('add_column', None, 'news', Column('author', String(length=100), table=<news>))]
$ echo $?
255
```

Усі 363 тести зелені: тестові бази створюються з моделей (`Base.metadata.create_all`), тож колонка в них є. У продакшні ж схему робить `migrate` (крок 11) — і першої ж вставки з `author` база не зрозуміє. Цю помилку бачить лише `alembic check`. Виправлення — `alembic revision --autogenerate -m "…"` і перечитати міграцію очима (`CLAUDE.md` кроку).

## `mypy --strict` { #types }

```yaml title="news_hub.yml → job types"
      - run: pip install -r requirements-dev.txt
      - run: mypy --strict news_hub
```

```text
$ mypy --strict news_hub
Success: no issues found in 26 source files
```

Окремий job, а не крок у `tests`: помилка типів і падіння тесту — різні причини, і в PR їх видно окремими рядками.

## Образ і smoke-тест стеку { #smoke }

Тести перевіряють код. Але користувач бачить зібрану систему: образ, Compose, nginx, міграції, справжню PostgreSQL. Job `docker` перевіряє саме її:

```yaml title="news_hub.yml → job docker"
  docker:
    name: образ і smoke-тест Compose
    needs: tests                     # образ збираємо, лише коли код пройшов тести
    ...
      - run: pip install -r requirements-dev.txt
      - name: тести образу (крок 10)
        run: pytest -m docker -q
      - name: .env для smoke — випадкові секрети, пароль адміна замасковано в журналі
        run: |
          password="$(openssl rand -hex 16)"
          echo "::add-mask::$password"
          echo "ADMIN_PASSWORD=$password" >> "$GITHUB_ENV"
          ADMIN_PASSWORD="$password" HTTP_PORT=8080 python scripts/make_env.py
      - name: smoke — увесь стек через nginx (крок 11)
        run: ./scripts/smoke.sh
```

1. **`pytest -m docker`** — 6 тестів образу з кроку 10: у ньому немає `.env`, `tests`, кешів, dev-залежностей; користувач `10001`, код належить root, том `/data` — користувачу; HEALTHCHECK стає `healthy`; `docker stop` завершується вчасно; `alembic upgrade head` працює на томі.
2. **`scripts/make_env.py`** — `.env` з `.env.example`: випадкові `POSTGRES_PASSWORD` і `JWT_SECRET`, bcrypt-хеш пароля адміна, `HTTP_PORT`. Значення — в одинарних лапках (у хеші є `$`, крок 11). Існуючий `.env` не перезаписує. Як тут обходяться з паролем — [розділ 4](permissions_and_publish.md#secrets).
3. **`scripts/smoke.sh`** — піднімає стек і проходить шлях користувача **через nginx**.

```bash title="scripts/smoke.sh (скорочено)"
set -euo pipefail
cleanup() { …; docker compose down -v --remove-orphans; }   # завжди: і при успіху, і при помилці
trap cleanup EXIT                  # при помилці спершу ps -a і журнали — їх видно в CI

docker compose up -d --build --wait --wait-timeout 180

check "готовність через nginx" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$base/health/ready")"
check "nginx відповідає" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$base/nginx-health")"
token="$(curl -sf -X POST "$base/api/admin/token" … | python3 -c '…["access_token"]')"
check "вхід адміна" true "…"
check "запис без токена" 401 "…"
check "збір зі знімка" 168 "$saved"
check "новини в PostgreSQL" '{"count":168}' "$(curl -sf "$base/api/news/count")"

check "/docs на сервері закрито (DOCS_ENABLED=false)" 404 "$(curl -s -o /dev/null -w '%{http_code}' "$base/docs")"
check "заголовки безпеки через nginx" nosniff \
    "$(curl -sI "$base/api/news/count" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-content-type-options" {print $2}')"
check "nginx без версії" "nginx" \
    "$(curl -sI "$base/nginx-health" | tr -d '\r' | awk -F': ' 'tolower($1)=="server" {print $2}')"

check "база й Redis без портів назовні" "" "$(docker compose ps postgres redis --format '{{.Ports}}' | grep -- '->' || true)"
echo "smoke: усе гаразд"
```

| Перевірка | Що доводить |
|---|---|
| `/health/ready` через nginx → 200 | nginx проксює до api, api бачить базу й Redis (крок 10) |
| `/nginx-health` → 200 | сам nginx живий |
| вхід адміна | хеш із `.env` дійшов до api цілим — `$` у лапках не зіпсувався (крок 11) |
| запис без токена → 401 | захист запису працює за nginx так само, як у тестах (крок 8) |
| збір зі знімка → 168, `count` → 168 | шлях запит → api → PostgreSQL, схема з міграцій сервісу `migrate` |
| `/docs` → 404 | Compose справді передав `DOCS_ENABLED=false` (крок 11): карти API на сервері немає. Тест `test_docs_enabled` перевіряє лише функцію, а не `docker-compose.yml` |
| `X-Content-Type-Options: nosniff` через nginx | заголовки безпеки застосунку ([крок 8](../08_security/admin_jwt.md#security-headers)) доходять до клієнта: nginx їх не губить і не перезаписує |
| `Server: nginx` без версії | `server_tokens off` у `nginx.conf` діє (крок 11) |
| база й Redis без портів | `docker-compose.yml` не відкрив їх назовні (крок 11) |

Локальний запуск (`COMPOSE_PROJECT_NAME=nh-step12-smoke`, щоб не зачепити інші стеки; у CI проєкт зветься `news_hub`, з `name:` у `docker-compose.yml`):

```text
$ ADMIN_PASSWORD=… ./scripts/smoke.sh
 ...                                          ← docker compose up: postgres, redis — Healthy; migrate — Exited; api, nginx — Healthy
✓ готовність через nginx
✓ nginx відповідає
✓ вхід адміна
✓ запис без токена
✓ збір зі знімка
✓ новини в PostgreSQL
✓ /docs на сервері закрито (DOCS_ENABLED=false)
✓ заголовки безпеки через nginx
✓ nginx без версії
✓ база й Redis без портів назовні
smoke: усе гаразд
```

Заголовки безпеки перевіряються на звичайному `GET`: `curl -s -D - -o /dev/null` друкує заголовки й викидає тіло. Перша версія перевірки брала `curl -sI`, тобто `HEAD`, а `/api/news/count` на `HEAD` відповідає `405 Method Not Allowed`. Перевірка проходила, бо заголовки є й на помилці, але дивилась не на ту відповідь, яку отримує клієнт. Для `/nginx-health` лишився `curl -sI`: там відповідає сам nginx, і `HEAD` він приймає.

Після нього `docker ps -a` не показує жодного контейнера `nh-step12-smoke-*`, томів теж немає: `trap cleanup EXIT` прибрав `down -v`.

### Результат: smoke ловить те, чого не бачать тести { #smoke-catches }

У копії кроку «для зручності налагодження» відкриваємо порт бази:

```yaml title="docker-compose.yml (зміна в копії)"
  postgres:
    ...
    ports: ["127.0.0.1:55452:5432"]
    networks: [backend]
```

Запуск зроблено до трьох перевірок безпеки вище; з ними перед `✗` ідуть ще три рядки `✓`, решта — так само:

```text
✓ готовність через nginx
✓ nginx відповідає
✓ вхід адміна
✓ запис без токена
✓ збір зі знімка
✓ новини в PostgreSQL
✗ база й Redis без портів назовні: очікували , отримали 127.0.0.1:55452->5432/tcp
--- smoke впав (код 1): стан і журнали ---
NAME                         IMAGE                COMMAND                  SERVICE    CREATED          STATUS                      PORTS
nh-step12-smoke-api-1        news_hub:12          "uvicorn news_hub.ap…"   api        26 seconds ago   Up 18 seconds (healthy)     8000/tcp
nh-step12-smoke-migrate-1    news_hub:12          "alembic upgrade head"   migrate    26 seconds ago   Exited (0) 18 seconds ago
nh-step12-smoke-nginx-1      nginx:1.27-alpine    "/docker-entrypoint.…"   nginx      26 seconds ago   Up 11 seconds (healthy)     0.0.0.0:18082->80/tcp, [::]:18082->80/tcp
nh-step12-smoke-postgres-1   postgres:16-alpine   "docker-entrypoint.s…"   postgres   27 seconds ago   Up 25 seconds (healthy)     127.0.0.1:55452->5432/tcp
nh-step12-smoke-redis-1      redis:7-alpine       "docker-entrypoint.s…"   redis      27 seconds ago   Up 25 seconds (healthy)     6379/tcp
```

Жоден з 363 тестів цього не бачить: вони не читають `docker-compose.yml`. А `cleanup` при помилці спершу друкує `docker compose ps -a` і журнали — у CI це перше, що прочитаєш у червоному job.

## Залежності й секрети: job `supply-chain` { #supply-chain }

**Задача.** Усі jobs вище перевіряють **наш** код. Але в образі — ще 70 чужих пакетів, і `requirements.txt` з `>=` не каже, які саме версії туди потрапили: сьогодні одні, після нового релізу на PyPI — інші, і образ, зібраний у `publish`, може відрізнятися від перевіреного в `docker`. Про вразливість у пакеті, який стоїть в образі, ми дізнаємось лише випадково. А секрет, який колись закомітили й наступним комітом «видалили», лишається в історії git — і в кожному клоні.

### Lock: точні версії й хеші { #lock }

**Зміна.** Поруч з `requirements.txt` — `requirements.lock`, згенерований `uv`:

```bash
uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock
```

```text title="requirements.lock (фрагмент)"
# This file was autogenerated by uv via the following command:
#    uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock
aiofiles==25.1.0 \
    --hash=sha256:… \
    --hash=sha256:…
    # via aiogram
…
google-genai==2.33.0 ; python_full_version < '3.11' \
…
google-genai==3.2.0 ; python_full_version >= '3.11' \
…
```

У ньому 80 записів для 70 пакетів: прямі залежності **і** залежності залежностей, кожна — точна версія і sha256 кожного дозволеного файлу (wheel під кожну платформу, sdist). І образ ставить уже його:

```dockerfile title="Dockerfile (фрагмент)"
#    Крок 12: не requirements.txt (діапазони «>=»: сьогодні одна версія, завтра інша), а requirements.lock —
#    точні версії всіх пакетів разом із залежностями залежностей і sha256 кожного файлу. --require-hashes:
#    підмінений на PyPI чи по дорозі пакет не встановиться. Оновити: uv pip compile (команда — у файлі).
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
```

- **`--require-hashes`** — pip ставить файл, лише якщо його sha256 є в lock. Підмінений на дзеркалі, на PyPI (перезалити ту саму версію не можна, але новий файл до неї додати — так) чи по дорозі пакет не встановиться: хеш не збіжеться.
- **`--universal --python-version 3.10`** — lock для **всіх** платформ і версій Python, які обіцяє проєкт, починаючи з 3.10, а не лише для машини, де його згенерували. Де версії мусять різнитися, `uv` пише обидві з маркером: 10 пакетів мають два записи, як `google-genai` вище (на 3.10 найновіша сумісна — 2.33.0, на 3.11+ — 3.2.0) — та сама причина, що й SQLAlchemy 2.0 / 2.1 у [matrix](#matrix). Образ на `python:3.12-slim` бере рядки з `>= '3.11'`. Lock, згенерований на Python 3.13 без `--universal`, на 3.10 просто не встановився б.
- **`requirements.txt` лишається з `>=`.** Це різні обіцянки: `requirements.txt` — «з якими версіями `news_hub` працює» (діапазон; нижні межі перевіряє `min-versions`, верхні — `tests` з найновішими), `requirements.lock` — «що саме стоїть в образі» (одна точка в цьому діапазоні). Якби `requirements.txt` закріпив точні версії, `min-versions` і `tests` перевіряли б одне й те саме, а про несумісність з новим релізом залежності ми дізнались би лише тоді, коли оновили б lock.
- **Lock оновлюють свідомо.** `uv pip compile` бере версії з наявного lock і змінює його, лише коли цього вимагає `requirements.txt`. Оновити все до найновішого — `--upgrade`; один пакет — `--upgrade-package <назва>`. Тести в CI ставлять `requirements-dev.txt` (діапазони) — тобто перевіряють і найновіші версії, і найменші; lock — те, що з цього діапазону їде в образ.

### Результат { #supply-chain-result }

Job складається з трьох перевірок:

```yaml title="news_hub.yml → job supply-chain"
  supply-chain:
    name: залежності й секрети
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0             # уся історія: секрет, видалений наступним комітом, у git лишається
      - uses: astral-sh/setup-uv@v6
      - name: requirements.lock відповідає requirements.txt
        # uv бере версії з наявного lock: файл змінюється, лише коли змінився requirements.txt
        run: |
          uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock
          git diff --exit-code -- requirements.lock
      - name: відомі вразливості в залежностях образу (pip-audit, база PyPA)
        run: uvx pip-audit==2.10.1 -r requirements.lock --require-hashes --disable-pip --progress-spinner off
      - name: секрети в історії git (gitleaks; навчальні значення — .gitleaks.toml)
        working-directory: .
        run: >-
          docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/repo:ro"
          ghcr.io/gitleaks/gitleaks:v8.30.1 git /repo --config /repo/.gitleaks.toml --redact --no-banner
```

**1. Lock відповідає `requirements.txt`.** Хтось додав залежність у `requirements.txt`, а lock не перегенерував — образ зібрався б без неї. CI генерує lock заново і порівнює з закоміченим. У копії кроку, в чистому git: без змін — `git diff --exit-code` мовчить і повертає 0; додамо `orjson>=3.10` у `requirements.txt` і згенеруємо:

```text
$ uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock -q
$ git diff --exit-code --stat -- requirements.lock
 requirements.lock | 61 +++++++++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 61 insertions(+)
$ echo $?
1
```

Підняти межу, яку lock уже задовольняє (`PyJWT>=2.10`, коли в lock і так новіша), — lock не змінюється, і job зелений: обидва файли досі кажуть правду.

**2. `pip-audit`** звіряє кожну версію з lock з базою вразливостей PyPA (Python Packaging Advisory Database). Перевіряється саме lock — те, що стоїть в образі, а не те, що випадково стоїть на машині CI. `--disable-pip` і `--require-hashes`: pip-audit не ставить пакети, щоб дізнатися залежності, — у lock вони вже всі. Версія pip-audit — точна (`==2.10.1`), як і все в CI: новий реліз інструмента не має змінювати результат без нашого коміту.

```text
$ uvx pip-audit==2.10.1 -r requirements.lock --require-hashes --disable-pip --progress-spinner off
No known vulnerabilities found
```

Коли базу поповнять і вразливість знайдеться в нашій версії, job почервоніє **без жодної зміни коду** — на наступному PR. Так і має бути: виправлення — `uv pip compile --upgrade-package <пакет>` і новий lock.

**3. gitleaks** шукає секрети (ключі API, токени, приватні ключі) за понад сотнею стандартних правил. `fetch-depth: 0` — уся історія, а не лише останній коміт: секрет, «видалений» наступним комітом, у git лишається, і його бачить кожен, хто склонує репозиторій. Образ gitleaks — з точною версією; репозиторій змонтовано лише для читання (`:ro`), `--redact` ховає знайдене значення з журналу, бо журнали Actions публічного репозиторію бачать усі. З кореня репозиторію:

```text
$ docker run --rm -v "$PWD:/repo:ro" ghcr.io/gitleaks/gitleaks:v8.30.1 git /repo --config /repo/.gitleaks.toml --redact --no-banner
5:27AM INF 25 commits scanned.
5:27AM INF scanned ~5916657 bytes (5.92 MB) in 10.6s
5:27AM INF no leaks found
```

Без allowlist, лише стандартні правила — `WRN leaks found: 7`. Усі сім — навчальні значення, які книга показує навмисно: підроблений токен `alg: none` з тестів, токен «olena», підписаний одноразовим секретом прикладу, одноразовий `JWT_SECRET` перевірочного стеку і явно підроблений секрет прикладу налаштувань. Вони — у `.gitleaks.toml` у корені репозиторію:

```toml title=".gitleaks.toml (фрагмент)"
[extend]
useDefault = true

[[allowlists]]
description = "навчальні значення книги, не секрети"
regexes = [
  # JWT з alg: none — тести перевіряють, що такий токен відхиляється (test_admin_api.py, кроки 8–12)
  '''eyJhbGciOiJub25lIn0\.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9\.''',
  …
]
```

Кожне значення — **точним рядком**, а не винятком на цілу папку `tests/` чи `docs/`: справжній секрет, покладений туди, сканер усе одно знайде. Тому й `.gitleaks.toml` — у `paths` тригерів workflow: зміна allowlist — теж привід перевірити все.

**`publish` чекає й на `supply-chain`.** `needs: [tests, min-versions, postgres, types, supply-chain, docker]` — образ з пакетом з відомою вразливістю чи з комітом із секретом у реєстр не потрапить ([розділ 3](order_and_parallel.md#needs)).

## Зелений CI, що нічого не перевіряє { #or-true }

Найнебезпечніша помилка в workflow — крок, який не може впасти:

```yaml
      - run: pytest || true
```

```text
$ bash -c 'set -e; false || true; echo "після || true код: $?"'
після || true код: 0
```

`|| true` робить код виходу нульовим за будь-якого результату. Тести можуть падати скільки завгодно — CI зелений. Зелений CI, що нічого не перевіряє, гірший за відсутній: йому вірять. Так само небезпечні `continue-on-error: true` на кроці з тестами і `pytest -x … ; echo done` в одному `run:` без `set -e`.

## Правило { #rule }

!!! tip "Правило"
    Кожна обіцянка проєкту — свій job: версії Python — matrix, нижні межі — `uv --resolution lowest-direct`, продакшн-база — `services` з healthcheck і `alembic check`, типи — `mypy --strict`, зібрана система — тести образу й smoke через nginx; те, що їде в образ, — lock з хешами, `pip-audit` і gitleaks по всій історії. Тести без списку руками, один прогін, без `|| true`. Усе, що робить job, запускається локально тими самими командами.

**Далі:** [Порядок і паралельність](order_and_parallel.md).
