# Команди

Команди з README кроків, `pytest.ini`, `Dockerfile`, `docker-compose*.yml`, `scripts/` і
`.github/workflows/news_hub.yml`. Усі запускаються **з папки кроку** (`cd steps/NN_<тема>`): там `pytest.ini`
(`pythonpath = .`), `alembic.ini` і пакет `news_hub`. «Крок» — з якого кроку команда працює.

## Встановлення { #install }

| Команда | Що робить | Крок |
|---|---|---|
| `python -m venv .venv && source .venv/bin/activate` | віртуальне оточення (Windows: `.venv\Scripts\activate`) | 1 |
| `pip install -r requirements.txt` | залежності кроку | 1–9 |
| `pip install -r requirements-dev.txt` | застосунок + pytest, mypy, fakeredis (`requirements.txt` — лише те, що йде в образ) | 10–12 |
| `uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock` | точні версії всіх 70 пакетів образу з sha256; запускати після кожної зміни `requirements.txt` | 12 |
| `pip install --require-hashes -r requirements.lock` | те, що робить Dockerfile кроку 12: пакет без хешу чи з іншим хешем — помилка | 12 |
| `pip install -r requirements-docs.txt` | MkDocs для книги (корінь репозиторію) | — |

Локальне оточення з нуля — [Локальне налаштування](../00_getting_started/local_setup.md).

## Запуск { #run }

| Команда | Що робить | Крок |
|---|---|---|
| `uvicorn news_hub.api:app --reload` | API на `http://127.0.0.1:8000`, `/docs`; перезапуск при зміні коду | 2 |
| `uvicorn news_hub.api:app --port 8010` | інший порт, якщо 8000 зайнятий | 2 |
| `docker compose up -d db` | PostgreSQL для розробки (сервіс `db`) | 3–10 |
| `docker compose up -d db redis` | PostgreSQL і Redis | 4–10 |
| `export DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub` | API і Alembic — у PostgreSQL (Windows: `set …`) | 3 |
| `export REDIS_URL=redis://localhost:6379/0` | Redis; без нього — `REDIS_URL=fakeredis://` | 4 |
| `export GEMINI_API_KEY=…` | ключ для аналізу; для розробки без мережі — `LLM_PROVIDER=fake` | 7 |
| `python -m news_hub.bot` | бот у режимі polling (знімає webhook) | 9 |
| `python -m tests.telegram_twin --port 8081` | двійник Telegram на `127.0.0.1:8081`; з ним `TELEGRAM_API_URL=http://127.0.0.1:8081` | 9 |
| `curl -X POST localhost:8081/_twin/say -d '{"text": "/news", "chat_id": 1001}'` | «користувач» пише боту | 9 |
| `curl localhost:8081/_twin/sent?chat_id=1001` | що відповів бот | 9 |
| `curl localhost:8000/health/ready` | `{"status":"ok","checks":{"database":"ok","redis":"ok"}}` | 10 |

Перевірка даних кроку 1 без сервера:

```bash
python -c "from news_hub.snapshot import load_snapshot; from news_hub.models import validate_news; print([len(x) for x in validate_news(load_snapshot())])"
```

## Секрети { #secrets }

| Команда | Що дає | Крок |
|---|---|---|
| `python -m news_hub.security` | питає пароль → рядки `ADMIN_PASSWORD_HASH='$2b$12$…'` і `JWT_SECRET='…'` (в одинарних лапках) | 8 |
| `python -m news_hub.security --env-file` | ті самі рядки без лапок — для `docker run --env-file` | 10 |
| `python -c 'import secrets; print(secrets.token_urlsafe(48))'` | випадковий секрет: `WEBHOOK_SECRET`, `TELEGRAM_WEBHOOK_SECRET` | 8, 9 |
| `export ADMIN_PASSWORD_HASH='$2b$12$…' JWT_SECRET='…'` | у shell — лише одинарні лапки | 8 |

Вхід і запит з токеном:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/admin/token -H 'Content-Type: application/json' \
  -d '{"username": "admin", "password": "…"}' | python -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
curl -X POST localhost:8000/api/scrape -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"source": "snapshot"}'
```

## Тести { #tests }

| Команда | Що запускає | Крок |
|---|---|---|
| `pytest` | усе, крім `llm` (з кроку 7) і `docker` (з кроку 10) — `addopts` у `pytest.ini`; SQLite у пам'яті, fakeredis, локальні HTTP-сервери, двійник Telegram, `FakeLLM` | 1 |
| `pytest -q` | те саме, коротко | 1 |
| `pytest -m unit` | лише швидкі: без бази, Redis і мережі | 5 |
| `pytest -m integration` | API разом з базою й Redis | 5 |
| `pytest -m llm` | справжні виклики LLM (ключ, витрачає квоту); без ключа — пропускаються | 7 |
| `pytest -m docker` | тести образу: збирає й запускає контейнер (потрібен Docker) | 10 |
| `pytest --cov=news_hub` | покриття; налаштування — `.coveragerc` (`concurrency = thread,greenlet`) | 5 |
| `pytest --markers` | список маркерів (одруківку в `-m` pytest не перевіряє) | 5 |
| `pytest tests/unit/test_models.py -q` | один файл | 1 |
| `pytest -k breaker` | тести, в імені яких є `breaker` | 1 |
| `TEST_DATABASE_URL=postgresql+asyncpg://… pytest` | інтеграційні тести на PostgreSQL | 3 |
| `TEST_REDIS_URL=redis://localhost:6379/15 pytest` | на справжньому Redis (гонки, яких fakeredis не покаже) | 4 |

Маркери оголошено в `pytest.ini`: `unit`, `integration`, `llm`, `docker`. Шари тестів —
[крок 5](../tutorials/05_api_testing/test_layers.md).

## Типи { #mypy }

| Команда | Крок |
|---|---|
| `mypy --strict news_hub` | 1 (у CI — job `mypy --strict` кроку 12) |

## Alembic { #alembic }

| Команда | Що робить | Крок |
|---|---|---|
| `alembic upgrade head` | застосувати всі міграції (з тим самим `DATABASE_URL`, що в сервера) | 3 |
| `alembic revision --autogenerate -m "опис"` | нова міграція з різниці `tables.py` ↔ база; **прочитати** перед комітом | 3 |
| `alembic downgrade -1` | відкотити одну міграцію | 3 |
| `alembic current`, `alembic history` | поточна ревізія, список | 3 |
| `alembic check` | чи є зміни моделей без міграції (CI, job `postgres`) | 12 |

Адресу бази `migrations/env.py` бере з `news_hub.db.DATABASE_URL`, не з `alembic.ini`.
Докладно — [Міграції Alembic](../tutorials/03_sqlalchemy_alembic/alembic.md).

## Docker { #docker }

| Команда | Що робить | Крок |
|---|---|---|
| `docker build -t news_hub:12 .` | образ | 10 |
| `docker network create news` | мережа для контейнерів API і Redis | 10 |
| `docker run -d --name redis --network news redis:7-alpine` | Redis у тій самій мережі | 10 |
| `docker run --rm -v news_data:/data news_hub:12 alembic upgrade head` | схема бази на томі | 10 |
| `docker run -d --name api --network news -p 8000:8000 -v news_data:/data -e REDIS_URL=redis://redis:6379/0 --env-file .env news_hub:12` | API в контейнері; `.env` — рядки з `python -m news_hub.security --env-file` | 10 |
| `docker stop api` | `SIGTERM` → uvicorn завершується сам за 1–2 с | 10 |
| `docker logs -f api` | журнал | 10 |

Докладно — [крок 10](../tutorials/10_docker/index.md).

## Compose { #compose }

| Команда | Що робить | Крок |
|---|---|---|
| `cp .env.example .env` | і заповнити: `POSTGRES_PASSWORD`, рядки з `python -m news_hub.security` | 11 |
| `docker compose up -d --build --wait` | `postgres` → `migrate` → `api` (healthy) → `nginx`; і оновлення після `git pull` | 11 |
| `curl localhost/health/ready` | готовність через nginx | 11 |
| `docker compose ps` | стан і healthcheck сервісів | 11 |
| `docker compose logs -f api` | журнал API; `logs migrate` — чому впала міграція | 11 |
| `docker compose down` | зупинити; дані лишаються в томі `pgdata` (`down -v` видалить і їх) | 11 |
| `docker compose --profile polling up -d` | ще й бот у режимі polling | 11 |
| `docker compose --profile twin up -d` | двійник Telegram (`BOT_TOKEN=123456:TEST-TOKEN`, `TELEGRAM_API_URL=http://twin:8081`) | 11 |
| `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis` | лише база й Redis на `127.0.0.1` для `uvicorn --reload` | 11 |
| `docker compose exec nginx nginx -s reload` | nginx заново визначає адреси `api` (після `--scale`) | 11 |

Докладно — [крок 11](../tutorials/11_compose_deploy/index.md).

## Скрипти { #scripts }

| Команда | Що робить | Крок |
|---|---|---|
| `./scripts/backup.sh [папка]` | `pg_dump` з контейнера → `backups/news_hub-YYYYMMDD-HHMMSS.sql.gz` | 11 |
| `./scripts/restore.sh backups/news_hub-….sql.gz` | **замінює** дані бази бекапом, очищає кеш Redis (`FLUSHDB`) | 11 |
| `ADMIN_PASSWORD=… python scripts/make_env.py` | `.env` з випадковими `POSTGRES_PASSWORD`, `JWT_SECRET` і хешем пароля; існуючий не перезаписує | 12 |
| `ADMIN_PASSWORD=… ./scripts/smoke.sh` | піднімає стек, перевіряє через nginx готовність, вхід, збір, базу без портів назовні, `/docs` → `404`, `X-Content-Type-Options: nosniff`, `Server: nginx` без версії; потім `down -v` | 12 |
| `git update-index --chmod=+x steps/12_ci_cd/scripts/smoke.sh` | біт виконання в git для файлів з NTFS (`core.filemode=false`) | 12 |

## Як CI { #ci }

Те саме, що робить `.github/workflows/news_hub.yml`, локально (з `steps/12_ci_cd`):

```bash
pip install -r requirements-dev.txt
pytest -m unit -q && pytest -q                      # job tests (Python 3.10 і 3.13)
mypy --strict news_hub                               # job mypy
alembic upgrade head && alembic check               # job postgres (з DATABASE_URL на PostgreSQL)
pytest -m docker -q                                  # job image
ADMIN_PASSWORD=… python scripts/make_env.py && ADMIN_PASSWORD=… ./scripts/smoke.sh
# job supply-chain («залежності й секрети»):
uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock
git diff --exit-code -- requirements.lock          # lock відповідає requirements.txt
uvx pip-audit==2.10.1 -r requirements.lock --require-hashes --disable-pip
docker run --rm -v "$(git rev-parse --show-toplevel):/repo:ro" ghcr.io/gitleaks/gitleaks:v8.30.1 \
  git /repo --config /repo/.gitleaks.toml --redact --no-banner
```

Мінімальні версії: `uv venv --python 3.10 .venv && uv pip install --resolution lowest-direct -r requirements-dev.txt
&& .venv/bin/pytest -q`. Докладно — [крок 12](../tutorials/12_ci_cd/what_to_check.md).

## Книга { #docs }

| Команда | Що робить |
|---|---|
| `mkdocs serve` | книга на `http://127.0.0.1:8000` з перезавантаженням |
| `mkdocs build --strict` | зібрати; попередження = помилка |
