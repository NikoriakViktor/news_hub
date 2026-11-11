# Крок 12. CI/CD на GitHub Actions

> **Код кроку:** [`steps/12_ci_cd`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/12_ci_cd), workflow — [`.github/workflows/news_hub.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/news_hub.yml) у корені репозиторію.
>
> **Передумови:** [Крок 11. Docker Compose і деплой](../11_compose_deploy/index.md) — є стек nginx → api → PostgreSQL + Redis, міграції окремим сервісом, бекап.

## Де ми зараз { #where }

За одинадцять кроків у `news_hub` з'явилось 343 тести (SQLite у пам'яті, fakeredis, локальні aiohttp-сервери, двійник Telegram, FakeLLM), `mypy --strict`, тести образу `pytest -m docker` (крок 10) і стек у Compose (крок 11). Кожна з цих перевірок ловить свій клас помилок.

Але всі вони працюють, лише коли хтось **не забуває** їх запустити. Забути легко: змінив одну функцію, «це ж дрібниця», push — і зламав те, що ламатися не мало. А деякі перевірки локально майже ніхто не запускає: тести на справжній PostgreSQL, на Python 3.10, з найменшими дозволеними версіями залежностей.

## Проблема { #problem }

Потрібен автомат, який:

- на **кожну** зміну сам збирає проєкт і проганяє всі перевірки — і показує результат прямо в pull request: зелена галочка чи червоний хрестик з журналом;
- перевіряє в кількох середовищах: дві версії Python, мінімальні версії залежностей, справжні PostgreSQL і Redis, зібраний образ і весь стек;
- не запускається, коли змінились файли, що до проєкту не стосуються, і не витрачає хвилини на застарілі прогони;
- має лише ті права, які потрібні, і не світить секрети в журналах;
- з `main` публікує готовий до встановлення артефакт — образ Docker у реєстрі.

Перше — **CI** (continuous integration): кожна зміна інтегрується з перевіркою. Останнє — **CD** (continuous delivery): те, що пройшло перевірки в `main`, автоматично стає артефактом, який можна поставити на сервер.

## Що додаємо { #what }

| Що | Де | Розділ |
|---|---|---|
| тригери: PR у будь-яку гілку, push лише в `main`, `paths`, `workflow_dispatch`, `concurrency` | `.github/workflows/news_hub.yml` | [Коли CI запускається](triggers.md) |
| шість jobs: matrix Python 3.10 / 3.13, мінімальні версії через `uv`, PostgreSQL + Redis і `alembic check`, `mypy --strict`, образ + smoke | `news_hub.yml`, `scripts/smoke.sh`, `scripts/make_env.py` | [Що саме перевіряти](what_to_check.md) |
| граф `needs`: що йде паралельно, що чекає; `fail-fast`, `timeout-minutes` | `news_hub.yml` | [Порядок і паралельність](order_and_parallel.md) |
| `permissions`, згенеровані секрети з `::add-mask::`, публікація образу в `ghcr.io` | `news_hub.yml` (`docker`, `publish`) | [Права, секрети, публікація](permissions_and_publish.md) |

## Архітектура: було → стало { #architecture }

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    subgraph OLD ["крок 11: перевірки — якщо не забули"]
        direction LR
        D0["розробник"] --> M0{"запустив pytest,<br>mypy, smoke?"}
        M0 -- "так" --> P0["push у main"]
        M0 -- "ні" --> X0["push у main<br>без перевірки"]
        P0 --> S0["сервер:<br>git pull, up --build"]
        X0 --> S0
    end
    subgraph NEW ["крок 12: перевірки — на кожен PR"]
        direction LR
        D1["розробник<br>push у гілку PR"] --> GA["GitHub Actions<br>news_hub.yml"]
        GA --> J["tests ×2, min-versions,<br>postgres, types → docker"]
        J --> PR{"усі jobs<br>зелені?"}
        PR -- "так" --> MG["merge у main"]
        PR -- "ні" --> FX["червоний хрестик<br>і журнал у PR"]
        MG --> PB["publish:<br>образ у ghcr.io"]
    end
    OLD --> NEW

    class D0,P0,S0,D1,GA,MG step
    class M0,PR decision
    class X0,FX error
    class J warning
    class PB success
```

- **Workflow лише вирішує, коли й де.** Кожен job запускає ті самі команди, що й ти локально: `pytest`, `mypy --strict news_hub`, `pytest -m docker`, `./scripts/smoke.sh`. Нової логіки перевірок у YAML немає.
- **Код застосунку не змінився.** Від кроку 11 до 12 у `news_hub/` змінився лише номер версії в `api.py` (`0.12.0`). Додались два скрипти й workflow.
- **CD тут — це публікація образу**, а не деплой. Сервер оновлюється, як у кроці 11, свідомою командою; [чому так](permissions_and_publish.md#auto-deploy).

## Файли кроку { #files }

| Файл | Що в ньому | Новий? |
|---|---|---|
| [`.github/workflows/news_hub.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/news_hub.yml) | 6 jobs: `tests` (matrix), `min-versions`, `postgres`, `types`, `docker`, `publish` | новий (у корені репозиторію) |
| [`scripts/smoke.sh`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/scripts/smoke.sh) | весь стек через nginx: готовність, вхід, `401` без токена, збір, база без портів; завжди `down -v` | новий |
| [`scripts/make_env.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/scripts/make_env.py) | `.env` з `.env.example` і випадковими секретами; хеш пароля адміна; існуючий `.env` не чіпає | новий |
| [`CLAUDE.md`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/CLAUDE.md) | команда smoke, де живе CI, правило «нижня межа в `requirements.txt` — справжня» | змінений |
| [`docker-compose.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/docker-compose.yml), [`Dockerfile`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/Dockerfile) | тег образу `news_hub:12` | змінений |
| [`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/news_hub/api.py) | `version="0.12.0"` | змінений |
| `news_hub/` (решта), `tests/`, `migrations/`, `nginx/` | з кроку 11 | без змін |

Поруч живуть ще два workflow репозиторію: [`steps.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/steps.yml) проганяє `pytest -q` у кожному кроці `steps/01…12` і в `examples/meteo_api` (Python 3.13, без Docker і PostgreSQL), [`docs.yml`](https://github.com/NikoriakViktor/news_hub/blob/main/.github/workflows/docs.yml) збирає цю книгу й публікує на GitHub Pages.

Повна структура проєкту й інструкції запуску всіх попередніх кроків — у [`README.md` кроку](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/README.md).

## Порядок читання { #reading-order }

1. [Коли CI запускається](triggers.md) — анатомія workflow, тригери, `paths`, `concurrency`.
2. [Що саме перевіряти](what_to_check.md) — шість jobs і що ловить кожен; мінімальні версії, `alembic check`, smoke.
3. [Порядок і паралельність](order_and_parallel.md) — граф `needs`, хвилі, `fail-fast`.
4. [Права, секрети, публікація](permissions_and_publish.md) — `GITHUB_TOKEN`, `::add-mask::`, образ у `ghcr.io`, автоматичний деплой чи ні.
5. [Контрольна точка](checkpoint.md) — перевірки, практика, самоперевірка.

Теорія до кроку — [Частина X. Docker, Compose і CI/CD](../../10_docker_and_ci/README.md) і [Частина VII. Тестування API](../../07_testing/README.md).

## Запуск { #run }

Усе, що робить CI, запускається локально тими самими командами. З папки кроку `steps/12_ci_cd`:

```bash
pip install -r requirements-dev.txt
pytest -m unit -q                 # 203 passed, 148 deselected — так починає job tests
pytest -q                         # 343 passed, 8 deselected
mypy --strict news_hub            # Success: no issues found in 26 source files
pytest -m docker -q               # 6 passed (потрібен Docker)

ADMIN_PASSWORD=… python scripts/make_env.py   # .env з випадковими секретами (якщо .env ще немає)
ADMIN_PASSWORD=… ./scripts/smoke.sh            # стек через nginx; наприкінці «smoke: усе гаразд» і down -v
```

Job `postgres` локально — з PostgreSQL 16 і Redis 7 (окремими контейнерами або з `docker-compose.dev.yml` кроку 11):

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub_test
export TEST_REDIS_URL=redis://localhost:6379/15
export DATABASE_URL=$TEST_DATABASE_URL
alembic upgrade head && alembic check     # No new upgrade operations detected.
pytest -q                                 # 343 passed
```

Job `min-versions` — через [`uv`](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.10 .venv
uv pip install --resolution lowest-direct -r requirements-dev.txt
.venv/bin/pytest -q                       # 343 passed
```

Усі ці числа — з локального запуску 2026-11-11 (виводи й нюанси — у [контрольній точці](checkpoint.md#check)). Завершених прогонів GitHub Actions для цього workflow на момент написання ще не було: перший прогін стояв у черзі.

## Порівняння з кроком 11 { #diff }

```bash
git diff --no-index --stat steps/11_compose_deploy steps/12_ci_cd
git diff --no-index steps/11_compose_deploy/scripts steps/12_ci_cd/scripts
```

На чистій копії репозиторію (без `__pycache__`):

```text
 steps/{11_compose_deploy => 12_ci_cd}/CLAUDE.md    |  5 ++-
 steps/{11_compose_deploy => 12_ci_cd}/Dockerfile   |  6 +--
 steps/{11_compose_deploy => 12_ci_cd}/README.md    | 29 +++++++++----
 .../docker-compose.yml                             |  4 +-
 .../news_hub/api.py                                |  2 +-
 /dev/null => steps/12_ci_cd/scripts/make_env.py    | 43 +++++++++++++++++++
 /dev/null => steps/12_ci_cd/scripts/smoke.sh       | 48 ++++++++++++++++++++++
 7 files changed, 122 insertions(+), 15 deletions(-)
```

Головна зміна кроку — поза папкою: `.github/workflows/news_hub.yml`. Workflow живе в корені репозиторію, бо GitHub шукає їх лише в `.github/workflows/`; на папку кроку він посилається через `env.PROJECT: steps/12_ci_cd` і `defaults.run.working-directory`.

## Що далі { #next }

Це останній крок Zero to Hero: `news_hub` пройшов шлях від парсера HTML до сервісу, який перевіряє кожну свою зміну. Далі:

- [News Hub Deep Dive](../../deep_dive/README.md) — та сама фінальна версія `steps/12_ci_cd`, але не «як ми сюди дійшли», а «як воно влаштоване зараз»: модулі, життєвий цикл запиту, модель даних, карта тестів, CI.
- [Практика](../../labs/README.md) — лабораторні до кожного кроку й фінальна лаба на `steps/12_ci_cd`.
