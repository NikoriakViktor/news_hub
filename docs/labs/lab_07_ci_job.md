# Лаба 7. Job CI: міграції туди й назад { #lab-07 }

| | |
|---|---|
| Основа | [крок 12](../tutorials/12_ci_cd/index.md) — `steps/12_ci_cd` і `.github/workflows/news_hub.yml` |
| Що тренує | новий job GitHub Actions (services, env, `needs`), shell-скрипт для CI, тест workflow як даних, `alembic downgrade` |
| Складність | ★★☆ |
| Орієнтовний час | 2 години |

## Мета { #goal }

**Задача.** Job `postgres` кроку 12 виконує `alembic upgrade head` і `alembic check` на чистій базі. Так перевіряються
`upgrade()` і відповідність моделей міграціям. А `downgrade()` не виконується ніде. Зламай `downgrade` міграції 0004,
забувши `op.drop_table('subscriptions')`, і всі jobs кроку 12 лишаться зеленими. Помилку побачать тоді, коли
відкат знадобиться на сервері, тобто в найгірший момент.

**Зміна.** Скрипт `scripts/migrations_roundtrip.sh`: `upgrade head` → `downgrade base` → `upgrade head` →
`alembic check`. Новий job `migrations` на PostgreSQL 16 запускає саме цей скрипт. `publish` чекає й на нього.

**Результат.** Той самий скрипт працює локально, і на SQLite (тест), і на PostgreSQL. Зламаний `downgrade` валить job,
а не відкат на сервері.

**Правило.** Код, який у CI ніколи не виконується, вважай неперевіреним. Логіка CI живе в скрипті репозиторію, який
можна запустити й локально; YAML лише викликає його.

## Звідки починаємо { #start }

Ця лаба змінює файл у корені репозиторію (`.github/workflows/news_hub.yml`), тож працюй у гілці самого репозиторію,
а не в копії кроку:

```bash
git switch -c lab-07-migrations
cd steps/12_ci_cd
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

```text
363 passed, 8 deselected
```

## Вимоги { #requirements }

1. `scripts/migrations_roundtrip.sh`: `set -euo pipefail`; переходить у корінь кроку (`cd "$(dirname "$0")/.."`);
   без `DATABASE_URL` зупиняється з поясненням. Далі рівно чотири команди в такому порядку:
   `alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head`, `alembic check`.
2. Job `migrations` у `.github/workflows/news_hub.yml`:
    - `services.postgres` — `postgres:16-alpine` з `pg_isready` у healthcheck, як у job `postgres`;
    - `env.DATABASE_URL` — `postgresql+asyncpg://…` на цю базу;
    - `timeout-minutes`;
    - крок `run: bash scripts/migrations_roundtrip.sh`. Саме `bash …`: на NTFS біт виконання файлу в git не
      зберігається сам, і `./scripts/…` впав би з `Permission denied`;
    - pytest тут не потрібен, тож встановлюється лише `requirements.lock` з `--require-hashes` — ті самі версії, що в
      образі (з ним Dockerfile кроку 12 і ставить залежності): міграції на сервері виконує саме образ.
3. `publish.needs` містить `migrations` — поруч з уже наявними `tests`, `min-versions`, `postgres`, `types`,
   `supply-chain` і `docker`: образ не публікується, якщо відкат міграцій зламаний.
4. `pyyaml` — явно в `requirements-dev.txt`: тест workflow його імпортує. Зараз він приходить транзитивно з
   `uvicorn[standard]`, але на це не варто покладатися. На `requirements.lock` і перевірку lock у job `supply-chain`
   це не впливає: lock генерується лише з `requirements.txt`, а залежності розробки в образ не йдуть.

## Критерії приймання { #acceptance }

Два файли тестів. Перший читає workflow як дані. Другий запускає скрипт на файлі SQLite.

```python title="tests/unit/test_ci_migrations_job.py"
"""Лаба 7: job «migrations» у CI. Читаємо workflow як дані — так само, як його читає GitHub."""
from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT = Path(__file__).resolve().parents[2]                   # steps/12_ci_cd
WORKFLOW = PROJECT.parents[1] / ".github" / "workflows" / "news_hub.yml"
SCRIPT = PROJECT / "scripts" / "migrations_roundtrip.sh"
ROUNDTRIP = ["alembic upgrade head", "alembic downgrade base", "alembic upgrade head", "alembic check"]


@pytest.fixture(scope="module")
def jobs() -> dict[str, Any]:
    if not WORKFLOW.exists():
        pytest.skip(f"немає {WORKFLOW}: тест читає workflow з кореня репозиторію")
    workflow: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]


def test_script_runs_the_round_trip_in_order() -> None:
    assert SCRIPT.exists(), f"немає {SCRIPT.relative_to(PROJECT)}"
    text = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text                               # перша ж помилка зупиняє скрипт
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("alembic ")]
    assert lines == ROUNDTRIP, lines


def test_migrations_job_uses_postgres_and_the_script(jobs: dict[str, Any]) -> None:
    job = jobs.get("migrations")
    assert job is not None, f"немає job migrations; є: {sorted(jobs)}"
    assert "postgres" in job.get("services", {}), "round-trip має йти на PostgreSQL, як прод"
    assert job.get("env", {}).get("DATABASE_URL", "").startswith("postgresql+asyncpg://")
    assert "timeout-minutes" in job
    commands = [step.get("run", "") for step in job["steps"]]
    assert any("scripts/migrations_roundtrip.sh" in command for command in commands), commands


def test_publish_waits_for_migrations(jobs: dict[str, Any]) -> None:
    assert "migrations" in jobs["publish"]["needs"]
```

```python title="tests/integration/test_migrations_roundtrip.py"
"""Лаба 7: той самий скрипт, що й у CI, — локально на файлі SQLite."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "scripts" / "migrations_roundtrip.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="немає bash")
def test_round_trip_on_sqlite(tmp_path: Path) -> None:
    assert SCRIPT.exists(), f"немає {SCRIPT.relative_to(PROJECT)}"
    env = os.environ | {
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_path / 'roundtrip.db'}",
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",   # alembic з того самого venv
    }
    result = subprocess.run(["bash", str(SCRIPT)], cwd=PROJECT, env=env, capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output[-3000:]
    assert "Running downgrade 0001 -> , " in output                  # справді дійшли до порожньої бази
    assert "No new upgrade operations detected." in output
```

**До змін:**

```text
$ pytest -q tests/unit/test_ci_migrations_job.py tests/integration/test_migrations_roundtrip.py
E       AssertionError: немає scripts/migrations_roundtrip.sh
E       AssertionError: немає job migrations; є: ['docker', 'min-versions', 'postgres', 'publish', 'supply-chain', 'tests', 'types']
E       AssertionError: assert 'migrations' in ['tests', 'min-versions', 'postgres', 'types', 'supply-chain', 'docker']
E       AssertionError: немає scripts/migrations_roundtrip.sh
FAILED tests/unit/test_ci_migrations_job.py::test_script_runs_the_round_trip_in_order
FAILED tests/unit/test_ci_migrations_job.py::test_migrations_job_uses_postgres_and_the_script
FAILED tests/unit/test_ci_migrations_job.py::test_publish_waits_for_migrations
FAILED tests/integration/test_migrations_roundtrip.py::test_round_trip_on_sqlite
4 failed in 0.21s
```

**Після змін:**

```text
$ pytest -q tests/unit/test_ci_migrations_job.py tests/integration/test_migrations_roundtrip.py
4 passed in 2.73s
$ pytest -q
367 passed, 8 deselected
$ pytest -m unit -q
215 passed, 160 deselected
$ mypy --strict news_hub
Success: no issues found in 26 source files
```

Тест workflow лежить у `tests/unit`, тож потрапляє в `pytest -m unit` кожного job `tests`. Якщо крок скопійовано
окремо від репозиторію, workflow немає, і тести job пропускаються (`skip`), а не падають.

**Той самий скрипт на PostgreSQL 16** (локально, у контейнері на вільному порту, як services у CI; залежності — як у job,
`pip install --require-hashes -r requirements.lock` у чистому venv):

```bash
docker run -d --name lab07-pg -e POSTGRES_DB=news_hub_migrations -e POSTGRES_USER=news \
  -e POSTGRES_PASSWORD=news -p 5587:5432 postgres:16-alpine
DATABASE_URL=postgresql+asyncpg://news:news@localhost:5587/news_hub_migrations bash scripts/migrations_roundtrip.sh
docker rm -f lab07-pg
```

```text
Running upgrade  -> 0001, news table — таблиця новин агрегатора (крок 3)
...
Running upgrade 0003 -> 0004, subscriptions — підписки чатів Telegram на ключові слова (крок 9)
Running downgrade 0004 -> 0003, subscriptions — підписки чатів Telegram на ключові слова (крок 9)
Running downgrade 0003 -> 0002, sources — RSS-джерела, які додає адмін (крок 8)
Running downgrade 0002 -> 0001, llm analysis — колонки аналізу LLM у таблиці news (крок 7)
Running downgrade 0001 -> , news table — таблиця новин агрегатора (крок 3)
Running upgrade  -> 0001, news table — таблиця новин агрегатора (крок 3)
...
No new upgrade operations detected.
```

**Що ловить job.** Зламай `downgrade()` у `migrations/versions/0004_subscriptions_table.py`, замінивши
`op.drop_table('subscriptions')` на `pass`. Тоді другий `upgrade head` спіткнеться об таблицю, яку відкат не
прибрав:

```text
Running upgrade 0003 -> 0004, subscriptions — підписки чатів Telegram на ключові слова (крок 9)
asyncpg.exceptions.DuplicateTableError: relation "subscriptions" already exists
```

На SQLite `test_round_trip_on_sqlite` падає з
`sqlite3.OperationalError: table subscriptions already exists`. Тим часом job `postgres` кроку 12 з тією самою
помилкою лишається зеленим: `downgrade` він не виконує.

Що **не** перевірено локально: сам прогін на GitHub. Правильність YAML перевіряє тест, а синтаксис виразів
`${{ … }}` і реальний запуск job побачиш лише в PR (вкладка **Actions**).

## Підказки { #hints }

??? tip "Чому скрипт, а не чотири рядки `run:` у YAML"
    Скрипт запускається однаково на твоїй машині, у тесті й у CI. YAML на `ubuntu-latest` локально не запустиш.
    Той самий принцип використовує `scripts/smoke.sh` кроку 12.

??? tip "`downgrade base` чи `downgrade -1`?"
    `-1` відкочує лише останню ревізію. `base` проходить `downgrade()` **кожної** міграції, а це і є мета job.
    Після нього база порожня, тож другий `upgrade head` перевіряє, що відкат прибрав усе, що створив `upgrade`.

??? tip "Окрема база для job"
    Кожен job отримує свій контейнер `services`, тож job `postgres` і `migrations` не заважають один одному, навіть
    якщо йдуть паралельно. Назва бази (`news_hub_migrations`) — лише для ясності в журналі.

??? tip "Як тест знаходить workflow"
    `tests/unit/test_ci_migrations_job.py` → `parents[2]` — `steps/12_ci_cd`, ще два рівні вгору — корінь репозиторію.
    `yaml.safe_load` читає ключ `on:` як `True` (YAML 1.1). Тест його не чіпає, тому це не заважає.

## Підхід до розв'язку { #solution }

??? success "Підхід до розв'язку"

    ```bash title="scripts/migrations_roundtrip.sh"
    #!/usr/bin/env bash
    # Міграції туди й назад на чистій базі: upgrade() і downgrade() кожної ревізії справді виконуються,
    # а схема після повторного upgrade збігається з моделями. Так запускає job migrations у CI.
    #   DATABASE_URL=postgresql+asyncpg://… ./scripts/migrations_roundtrip.sh
    set -euo pipefail

    cd "$(dirname "$0")/.."
    : "${DATABASE_URL:?задай DATABASE_URL — порожню базу, яку не шкода}"

    alembic upgrade head
    alembic downgrade base
    alembic upgrade head
    alembic check
    ```

    ```yaml title=".github/workflows/news_hub.yml (новий job, після postgres)"
      migrations:
        name: міграції туди й назад · PostgreSQL 16
        runs-on: ubuntu-latest
        timeout-minutes: 10
        services:
          postgres:
            image: postgres:16-alpine
            env:
              POSTGRES_DB: news_hub_migrations
              POSTGRES_USER: news
              POSTGRES_PASSWORD: news         # одноразова база CI; не секрет
            ports: ["5432:5432"]
            options: >-
              --health-cmd pg_isready
              --health-interval 5s
              --health-timeout 5s
              --health-retries 10
        env:
          DATABASE_URL: postgresql+asyncpg://news:news@localhost:5432/news_hub_migrations
        steps:
          - uses: actions/checkout@v5
          - uses: actions/setup-python@v6
            with:
              python-version: "3.13"
              cache: pip
              cache-dependency-path: ${{ env.PROJECT }}/requirements.lock
          # ті самі версії, що в образі: міграції в проді виконує саме образ (pytest тут не потрібен)
          - run: pip install --require-hashes -r requirements.lock
          - run: bash scripts/migrations_roundtrip.sh
    ```

    ```diff title=".github/workflows/news_hub.yml (publish)"
    -    needs: [tests, min-versions, postgres, types, supply-chain, docker]
    +    needs: [tests, min-versions, postgres, migrations, types, supply-chain, docker]
    ```

    ```text title="requirements-dev.txt (додати рядок)"
    pyyaml>=6.0            # тест workflow CI читає YAML; прийде й транзитивно з uvicorn[standard], але імпортуємо явно
    ```

    `working-directory: steps/12_ci_cd` уже задано в `defaults.run` workflow, тому `bash scripts/…` і
    `pip install … -r requirements.lock` спрацюють без `cd`.

## Що перевірити самому { #self-check }

- [ ] Обидва тести зелені, `pytest -q` — `367 passed`, `mypy --strict news_hub` чистий.
- [ ] Скрипт пройшов на PostgreSQL у контейнері, і в журналі є `Running downgrade 0001 -> ,`.
- [ ] Зламав `downgrade` міграції 0004 і побачив червоний скрипт і червоний `test_round_trip_on_sqlite`, а потім
      повернув як було.
- [ ] У PR на GitHub з'явився job «міграції туди й назад · PostgreSQL 16», а `publish` на push у `main` чекає на нього
      (граф jobs у вкладці **Actions**).
- [ ] Можеш пояснити, чому `alembic check` стоїть **після** другого `upgrade`, а не після першого.
- [ ] Подумай: що станеться з round-trip, якщо `downgrade` видаляє стовпець з даними? Чому для бази з даними
      відкат міграції — окреме рішення, а не автоматична дія?
