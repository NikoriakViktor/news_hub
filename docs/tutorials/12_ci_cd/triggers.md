# Коли CI запускається

> Крок 12 · розділ 1 з 4. Код: [`.github/workflows/news_hub.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/news_hub.yml) — блоки `on`, `concurrency`, `env`, `defaults`.
> Теорія: [Частина X. Docker, Compose і CI/CD](../../10_docker_and_ci/README.md).

## Задача { #task }

Workflow має запускатися на **кожен** PR, що змінює `steps/12_ci_cd`, — у яку б гілку цей PR не націлювали. І не запускатися, коли змінились лише книга чи інший крок. Кожен коміт має перевірятися **один** раз, а застарілий прогін — не займати раннер, коли в PR уже новий коміт.

Перш ніж міняти тригери, — з чого складається workflow.

## Анатомія workflow { #anatomy }

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    E["подія: push, pull_request,<br>workflow_dispatch"]
    F{"on: гілки, paths —<br>запускати?"}
    N["workflow не стартує:<br>у PR немає перевірки"]
    W["workflow = jobs"]
    J1["job: окрема чиста VM<br>runs-on: ubuntu-latest"]
    S1["services: контейнери<br>поруч з job"]
    ST["steps по черзі: uses (готова дія)<br>або run (команда)"]
    R{"код виходу кроку<br>= 0?"}
    OK["job зелений"]
    BAD["job червоний,<br>наступні кроки не йдуть"]
    E --> F
    F -- "так" --> W --> J1 --> ST --> R
    F -- "ні" --> N
    S1 -.-> J1
    R -- "так, усі кроки" --> OK
    R -- "ні" --> BAD

    class E,W,J1,S1,ST step
    class F,R decision
    class OK success
    class BAD error
    class N warning
```

| Поняття | Що це | У `news_hub.yml` |
|---|---|---|
| **workflow** | файл `.github/workflows/*.yml` у корені репозиторію | `name: news_hub — CI/CD` |
| **подія** (`on`) | що запускає workflow | `push`, `pull_request`, `workflow_dispatch` |
| **job** | набір кроків на окремій чистій віртуальній машині (runner); jobs ідуть паралельно, якщо немає `needs` | `tests`, `min-versions`, `postgres`, `types`, `docker`, `publish` |
| **step** | `uses: дія@версія` (готова дія з Marketplace) або `run: команда` | `actions/checkout@v5`, `run: pytest -q` |
| **services** | контейнери поруч з job, доступні на `localhost:порт` | PostgreSQL 16 і Redis 7 у job `postgres` |
| **matrix** | один job у кількох варіантах | `python: ["3.10", "3.13"]` |
| **secrets / `GITHUB_TOKEN`** | секрети репозиторію й тимчасовий токен прогону | `secrets.GITHUB_TOKEN` у `publish` |

Крок зелений, коли команда завершилась з кодом виходу `0`. Це той самий контракт, що в `set -e` у `scripts/smoke.sh` і `backup.sh` (крок 11):

```bash
bash -c 'set -euo pipefail; echo "крок 1"; false; echo "крок 2"'; echo "код виходу: $?"
```

```text
крок 1
код виходу: 1
```

`крок 2` не надрукувався: перша команда з ненульовим кодом зупинила скрипт. Так само в job: крок з кодом не `0` — червоний, наступні кроки не йдуть.

## Старт: workflow Django-книги { #start }

Основа workflow — `.github/workflows/django-tests.yml` з [Django-книги](https://nikoriakviktor.github.io/notes_chat_app/) (про це — коментар у першому рядку `news_hub.yml`). Скорочено:

```yaml title="notes_chat_app/.github/workflows/django-tests.yml (скорочено)"
on:
  push:
    branches: [ main, master ]
    paths: ['notes_app/**', 'notes_project/**', 'templates/**', 'static/**', 'requirements.txt', ...]
  pull_request:
    branches: [ main, master ]
    paths: [ ... ]
  workflow_dispatch:

jobs:
  unit-and-integration:
    runs-on: ubuntu-latest
    services:
      db:
        image: postgres:16-alpine
        env: {POSTGRES_DB: notes_db, POSTGRES_USER: notes_user, POSTGRES_PASSWORD: notes_pass}
        ports: [5432:5432]
        options: --health-cmd pg_isready ...
    env:
      DATABASE_URL: postgres://notes_user:notes_pass@localhost:5432/notes_db
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - uses: actions/cache@v4
        with: {path: ~/.cache/pip, key: ...}
      - run: pip install -r requirements.txt
      - run: python manage.py check
      - run: |
          python manage.py test \
            notes_app.tests.test_models \
            notes_app.tests.test_services \
            ...
      - run: |
          coverage run manage.py test notes_app.tests.test_models ...
          coverage report --show-missing
  selenium-e2e:
    needs: unit-and-integration
    services:
      selenium: {image: "selenium/standalone-chrome:latest", ...}
```

Тут уже багато правильного — це лишаємо:

- PostgreSQL як `services` з healthcheck — тести на тій самій базі, що в продакшні;
- `paths` — workflow не запускається, коли змінились файли, що до проєкту не стосуються;
- кеш pip, `workflow_dispatch` (кнопка «Run workflow»), `needs` — повільні E2E лише після швидких тестів;
- перевірка конфігурації (`manage.py check`) перед тестами.

А тригери, список тестів руками, подвійний прогін для покриття й відсутність `permissions` — міняємо. Тригери — тут, решта — у [наступних розділах](what_to_check.md#test-list).

## Зміна 1. `pull_request` без `branches` { #pull-request }

```yaml
  pull_request:
    branches: [ main, master ]
```

`branches` у `pull_request` — це гілка, **у яку** PR хочуть злити (base), а не гілка, з якої він прийшов. Коли одна робота продовжує іншу, ще не злиту, PR відкривають не в `main`, а в гілку попереднього PR. На такому PR цей workflow **не запуститься зовсім** — і червоного хрестика не буде, бо не буде й перевірки.

!!! warning "Відсутність перевірки виглядає як успіх"
    Червоний статус видно — його виправлять. Відсутній статус у PR без обов'язкових перевірок виглядає як «усе гаразд»: PR зливають, і ніхто не помічає, що CI не запускався.

У `news_hub.yml` `branches` у `pull_request` немає:

```yaml title=".github/workflows/news_hub.yml"
on:
  push:
    branches: [main]
    paths:
      - 'steps/12_ci_cd/**'
      - '.github/workflows/news_hub.yml'
      - '.gitleaks.toml'
  pull_request:                      # без branches: PR у будь-яку гілку (зокрема PR поверх іншого PR)
    paths:
      - 'steps/12_ci_cd/**'
      - '.github/workflows/news_hub.yml'
      - '.gitleaks.toml'
  workflow_dispatch:
```

## Зміна 2. `push` — лише `main` { #push }

Друга половина — `push`. Якщо `push` без обмеження гілок, кожен коміт у гілці PR перевіряється **двічі**: на подію `push` (у гілку) і на подію `pull_request` (у PR). Хвилини раннерів подвоюються, а статус у PR потрібен один.

Тому `push` — лише в `main`: це коміти, які вже злиті, і саме звідти йде публікація образу ([розділ 4](permissions_and_publish.md#publish)). Гілки PR перевіряє `pull_request`.

`workflow_dispatch` — кнопка **Run workflow** у вкладці Actions: запустити вручну, наприклад після збою раннера, без нового коміту.

## Зміна 3. `paths` — і сам workflow теж { #paths }

`paths` у `news_hub.yml` — три маски: усе в папці кроку, **сам файл workflow** і `.gitleaks.toml` у корені. Змінив перевірки — перевір, що вони працюють: інакше зламаний YAML доїде до `main` без жодного прогону. `.gitleaks.toml` — теж частина перевірок: розширений allowlist сканера секретів має пройти через job `supply-chain` ([розділ 2](what_to_check.md#supply-chain)), як і будь-яка інша зміна правил.

Інші кроки й книга до цього workflow не стосуються: їх перевіряють [`steps.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/steps.yml) (маска `steps/**`) і [`docs.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/docs.yml) (`docs/**`, `mkdocs.yml`, лише на `push`).

## Результат: які workflows запустяться { #result }

Щоб не гадати, тригери можна прочитати як дані. Скрипт нижче бере три файли з `.github/workflows/`, для кожного випадку (подія, гілка, змінений файл) перевіряє `on` → `branches` → `paths` і друкує, чи стартує workflow. Маски спрощені (`**` — будь-що, `*` — у межах однієї папки), для цих файлів цього досить.

```python title="triggers.py"
import re
import sys
from pathlib import Path

import yaml


def glob(pattern: str) -> re.Pattern[str]:
    rx = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    return re.compile(rx + "$")


def runs(wf: dict, event: str, branch: str, files: list[str]) -> bool:
    on = wf.get("on", wf.get(True))          # PyYAML читає ключ `on` як True
    if event not in on:
        return False
    rule = on[event] or {}
    if "branches" in rule and branch not in rule["branches"]:
        return False
    if "paths" in rule and not any(glob(p).match(f) for p in rule["paths"] for f in files):
        return False
    return True


workflows = {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(Path(sys.argv[1]).glob("*.yml"))}
cases = [
    ("pull_request", "main", ["steps/12_ci_cd/news_hub/api.py"]),
    ("pull_request", "feature-a", ["steps/12_ci_cd/news_hub/api.py"]),
    ("pull_request", "main", ["steps/11_compose_deploy/README.md"]),
    ("pull_request", "main", ["docs/tutorials/12_ci_cd/index.md"]),
    ("pull_request", "main", [".github/workflows/news_hub.yml"]),
    ("push", "feature-a", ["steps/12_ci_cd/news_hub/api.py"]),
    ("push", "main", ["steps/12_ci_cd/news_hub/api.py"]),
    ("push", "main", ["docs/tutorials/12_ci_cd/index.md"]),
]
print(f"{'подія':<13} {'гілка':<10} {'змінено':<34} " + " ".join(f"{n:<9}" for n in workflows))
for event, branch, files in cases:
    marks = " ".join(f"{'так' if runs(wf, event, branch, files) else 'ні':<9}" for wf in workflows.values())
    print(f"{event:<13} {branch:<10} {files[0]:<34} {marks}")
```

```text
$ python triggers.py .github/workflows
подія         гілка      змінено                            docs      news_hub  steps
pull_request  main       steps/12_ci_cd/news_hub/api.py     ні        так       так
pull_request  feature-a  steps/12_ci_cd/news_hub/api.py     ні        так       так
pull_request  main       steps/11_compose_deploy/README.md  ні        ні        так
pull_request  main       docs/tutorials/12_ci_cd/index.md   ні        ні        ні
pull_request  main       .github/workflows/news_hub.yml     ні        так       ні
push          feature-a  steps/12_ci_cd/news_hub/api.py     ні        ні        ні
push          main       steps/12_ci_cd/news_hub/api.py     ні        так       так
push          main       docs/tutorials/12_ci_cd/index.md   так       ні        ні
```

Для `pull_request` «гілка» — це base, куди PR зливають.

- Рядок 2: PR поверх іншого PR (base `feature-a`) перевіряється так само, як PR у `main`.
- Рядок 6: push у гілку PR сам по собі нічого не запускає — перевірку дає подія `pull_request`, один прогін на коміт.
- Рядок 4: зміна лише в книзі не запускає тестів; книгу збирає `docs.yml` після push у `main`.

Те саме з тригером Django-книги — повертаємо `branches: [main]` у `pull_request` копії `news_hub.yml`:

```text
подія         гілка      змінено                            news_hub
pull_request  main       steps/12_ci_cd/news_hub/api.py     так
pull_request  feature-a  steps/12_ci_cd/news_hub/api.py     ні
```

PR у `feature-a` лишився б без перевірки.

!!! note "`paths` і обов'язкові перевірки"
    Якщо в налаштуваннях гілки перевірка `news_hub — CI/CD` позначена обов'язковою (branch protection, required checks), а PR змінює лише `docs/`, workflow через `paths` не стартує — і обов'язкова перевірка лишається в стані «очікує», PR не зливається. Обов'язковими роблять перевірки, які запускаються на кожен PR, або прибирають `paths` у таких workflow.

## Зміна 4. `concurrency` — застарілий прогін скасовується { #concurrency }

```yaml
concurrency:                         # новий push у той самий PR скасовує попередній прогін
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

Група — назва workflow плюс `ref`: для PR це `refs/pull/<номер>/merge`, для push у `main` — `refs/heads/main`. Поки в групі йде прогін, а приходить новий, старий скасовується: результат для коміту, якого вже немає на вершині PR, нікому не потрібен.

!!! warning "Та сама група — і для `main`"
    Ключ однаковий і для push у `main`. Два злиття поспіль — і прогін першого скасовується разом з його `publish`; образ опублікує другий прогін, з новішого коміту. Для `latest` це те, що треба. Якщо ж кожен коміт `main` мусить отримати свій образ `sha-…`, скасування роблять лише для PR: `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`.

## Зміна 5. Одна папка — один рядок { #working-directory }

Workflow лежить у корені репозиторію, а проєкт — у `steps/12_ci_cd`. Щоб не писати `cd steps/12_ci_cd && …` у кожному кроці (і не забути це в одному з них):

```yaml
env:
  PROJECT: steps/12_ci_cd

defaults:
  run:
    working-directory: steps/12_ci_cd
```

- `defaults.run.working-directory` — для всіх `run:`: `pip install -r requirements-dev.txt`, `pytest`, `./scripts/smoke.sh` виконуються в папці кроку.
- `env.PROJECT` — для `with:` дій, яким `working-directory` не діє: `cache-dependency-path: ${{ env.PROJECT }}/requirements*.txt` (ключ кешу pip — з файлів залежностей кроку) і `context: ${{ env.PROJECT }}` у збірці образу.

## Правило { #rule }

!!! tip "Правило"
    `pull_request` — без `branches`, з `paths`, і в `paths` — сам файл workflow. `push` — лише `main`, звідки йде публікація. `concurrency` скасовує застарілі прогони. Відсутній прогін небезпечніший за червоний: він виглядає як успіх.

**Далі:** [Що саме перевіряти](what_to_check.md).
