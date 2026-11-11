# Що саме перевіряти

> Крок 12 · розділ 2 з 4. Код: [`.github/workflows/news_hub.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/news_hub.yml) (jobs `tests`, `min-versions`, `postgres`, `types`, `docker`), [`scripts/smoke.sh`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/scripts/smoke.sh), [`requirements.txt`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/requirements.txt).
> Теорія: [Частина VII. Тестування API](../../07_testing/README.md), [Частина X. Docker, Compose і CI/CD](../../10_docker_and_ci/README.md).

## Задача { #task }

Локально `pytest -q` проходить: 343 тести на SQLite у пам'яті й fakeredis, на тому Python і тих версіях пакетів, що стоять у тебе. Але `news_hub` обіцяє більше:

- `CLAUDE.md` кроку: «Python 3.10+»;
- `requirements.txt`: `fastapi>=0.121`, `pydantic>=2.9`, `sqlalchemy[asyncio]>=2.0.30`… — «працює з цими версіями й новішими»;
- у продакшні — PostgreSQL і справжній Redis, схема бази — з міграцій Alembic, а не з `create_all`;
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

Тут unit-тести справді йдуть двічі, але свідомо: 203 швидкі тести (у локальному запуску — 12 с) падають раніше, ніж стартують інтеграційні, і перша причина видна в журналі одразу. Покриття, коли потрібне, — одним прогоном (`pytest --cov=news_hub`), а не окремим повторним.

## Карта jobs { #jobs }

| Job (назва в PR) | Що робить | Що ловить |
|---|---|---|
| `pytest · Python 3.10` / `pytest · Python 3.13` (matrix) | `pytest -m unit`, потім `pytest` | код, що працює лише на новому (або лише на старому) Python, і пакети, що для різних Python ставляться різних версій |
| `pytest · мінімальні версії (Python 3.10)` | `uv pip install --resolution lowest-direct`, `pytest` | неправдиві нижні межі в `requirements.txt` |
| `pytest і Alembic · PostgreSQL 16 + Redis 7` | `alembic upgrade head`, `alembic check`, `pytest` | відмінності SQLite і PostgreSQL, fakeredis і Redis; змінену модель без міграції |
| `mypy --strict` | `mypy --strict news_hub` | помилки типів |
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

Matrix перевіряє не лише синтаксис мови. Той самий `pip install -r requirements-dev.txt` на різних Python ставить **різні** пакети. Локальний запуск 2026-11-11 (через `uv`, як нижче):

| | Python 3.10.19 | Python 3.13.17 |
|---|---|---|
| `sqlalchemy` | 2.0.57 | 2.1.8 |
| `fastapi`, `pydantic`, `aiogram` | 0.162.4, 2.13.5, 3.31.0 | 0.162.4, 2.13.5, 3.31.0 |
| `pytest -m unit -q` | 203 passed, 148 deselected | 203 passed, 148 deselected |
| `pytest -q` | 343 passed, 8 deselected | 343 passed, 8 deselected |

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
343 passed, 8 deselected, 30 warnings
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
news_hub/api.py:185: in <module>
    SessionDep = Annotated[AsyncSession, Depends(get_db, scope="function")]
E   TypeError: Depends() got an unexpected keyword argument 'scope'
=========================== short test summary info ============================
ERROR tests/integration - TypeError: Depends() got an unexpected keyword argu...
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
8 deselected, 1 error in 5.68s
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
343 passed, 8 deselected
```

А тепер «забули міграцію»: у копії кроку додаємо в `NewsRow` колонку й не пишемо міграції.

```python title="news_hub/tables.py (зміна в копії)"
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    author: Mapped[str | None] = mapped_column(String(100))      # нова колонка, міграції немає
```

```text
$ pytest -q
343 passed, 8 deselected in 21.45s
$ alembic upgrade head && alembic check
INFO  [alembic.autogenerate.compare.tables] Detected added column 'news.author'
ERROR [alembic.util.messaging] New upgrade operations detected: [('add_column', None, 'news', Column('author', String(length=100), table=<news>))]
FAILED: New upgrade operations detected: [('add_column', None, 'news', Column('author', String(length=100), table=<news>))]
$ echo $?
255
```

Усі 343 тести зелені: тестові бази створюються з моделей (`Base.metadata.create_all`), тож колонка в них є. У продакшні ж схему робить `migrate` (крок 11) — і першої ж вставки з `author` база не зрозуміє. Цю помилку бачить лише `alembic check`. Виправлення — `alembic revision --autogenerate -m "…"` і перечитати міграцію очима (`CLAUDE.md` кроку).

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
| база й Redis без портів | `docker-compose.yml` не відкрив їх назовні (крок 11) |

Локальний запуск (`COMPOSE_PROJECT_NAME=nh-step12-smoke`, щоб не зачепити інші стеки; у CI проєкт зветься `news_hub`, з `name:` у `docker-compose.yml`):

```text
$ ADMIN_PASSWORD=… ./scripts/smoke.sh
 ...
 Container nh-step12-smoke-postgres-1  Healthy
 Container nh-step12-smoke-redis-1  Healthy
 Container nh-step12-smoke-migrate-1  Exited
 Container nh-step12-smoke-api-1  Healthy
 Container nh-step12-smoke-nginx-1  Healthy
✓ готовність через nginx
✓ nginx відповідає
✓ вхід адміна
✓ запис без токена
✓ збір зі знімка
✓ новини в PostgreSQL
✓ база й Redis без портів назовні
smoke: усе гаразд
```

Після нього `docker ps -a` не показує жодного контейнера `nh-step12-smoke-*`, томів теж немає: `trap cleanup EXIT` прибрав `down -v`.

### Результат: smoke ловить те, чого не бачать тести { #smoke-catches }

У копії кроку «для зручності налагодження» відкриваємо порт бази:

```yaml title="docker-compose.yml (зміна в копії)"
  postgres:
    ...
    ports: ["127.0.0.1:55452:5432"]
    networks: [backend]
```

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

Жоден з 343 тестів цього не бачить: вони не читають `docker-compose.yml`. А `cleanup` при помилці спершу друкує `docker compose ps -a` і журнали — у CI це перше, що прочитаєш у червоному job.

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
    Кожна обіцянка проєкту — свій job: версії Python — matrix, нижні межі — `uv --resolution lowest-direct`, продакшн-база — `services` з healthcheck і `alembic check`, типи — `mypy --strict`, зібрана система — тести образу й smoke через nginx. Тести без списку руками, один прогін, без `|| true`. Усе, що робить job, запускається локально тими самими командами.

**Далі:** [Порядок і паралельність](order_and_parallel.md).
