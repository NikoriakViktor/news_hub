# Контрольна точка: крок 12

## Перевір, що крок робочий { #check }

Усе, що робить CI, — локально тими самими командами. З папки `steps/12_ci_cd`, як jobs `tests` і `types`:

```text
$ pytest -m unit -q -p no:cacheprovider
203 passed, 148 deselected in 12.46s
$ pytest -q -p no:cacheprovider
343 passed, 8 deselected in 29.66s
$ mypy --strict news_hub
Success: no issues found in 26 source files
```

Matrix `tests` — на обох версіях Python (окремі venv через `uv`, найновіші версії пакетів):

```text
Python 3.10.19:  203 passed, 148 deselected · 343 passed, 8 deselected
Python 3.13.17:  203 passed, 148 deselected · 343 passed, 8 deselected
```

Job `min-versions` (Python 3.10, `uv pip install --resolution lowest-direct`):

```text
$ .venv/bin/pytest -q
343 passed, 8 deselected, 30 warnings
```

Job `postgres` (PostgreSQL 16 і Redis 7 у контейнерах, змінні `TEST_DATABASE_URL`, `TEST_REDIS_URL`, `DATABASE_URL`):

```text
$ alembic upgrade head && alembic check
...
No new upgrade operations detected.
$ pytest -q
343 passed, 8 deselected
```

Job `docker` (потрібен Docker):

```text
$ pytest -m docker -q
6 passed, 345 deselected in 45.39s
$ ADMIN_PASSWORD=… HTTP_PORT=18082 python scripts/make_env.py
створено …/.env
$ ADMIN_PASSWORD=… ./scripts/smoke.sh
...
✓ готовність через nginx
✓ nginx відповідає
✓ вхід адміна
✓ запис без токена
✓ збір зі знімка
✓ новини в PostgreSQL
✓ база й Redis без портів назовні
smoke: усе гаразд
```

Усе — запуск 2026-11-11. Job `publish` локально не відтворюється: він пушить у `ghcr.io` з токеном прогону. Сам workflow на GitHub на момент написання ще не завершив жодного прогону — перший стояв у черзі.

## Чекліст { #checklist }

- [ ] Можеш пояснити, чому в `pull_request` немає `branches`, а в `push` — є.
- [ ] Знаєш, які з трьох workflows запустяться на PR, що змінює лише `docs/`, і на PR, що змінює `steps/12_ci_cd/news_hub/api.py`.
- [ ] `pytest -q` → 343 passed, `mypy --strict news_hub` → `Success`, `pytest -m docker -q` → 6 passed.
- [ ] Мінімальні версії через `uv` → 343 passed; знаєш, яку помилку дасть межа `fastapi>=0.115`.
- [ ] `alembic check` на чистій базі → `No new upgrade operations detected.`
- [ ] `./scripts/smoke.sh` закінчується `smoke: усе гаразд`, після нього `docker ps -a` не показує контейнерів стеку.
- [ ] Можеш намалювати три хвилі jobs і сказати, що станеться з `docker` і `publish`, якщо впаде `pytest · Python 3.10`.
- [ ] Знаєш, які права має токен у `tests` і в `publish`, і чому `contents: read` у `publish` повторено.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| PR без жодної перевірки `news_hub — CI/CD` | PR змінює лише файли поза `paths` — або (у старому тригері) націлений не в `main` | так і має бути для `docs/`; для коду перевір `paths` і що в `pull_request` немає `branches` |
| обов'язкова перевірка «очікує» вічно, PR не зливається | workflow з `paths` не стартував, а перевірка позначена required | обов'язковими — перевірки, що йдуть на кожен PR, або без `paths` |
| `./scripts/smoke.sh: Permission denied` (код 126) | файл на NTFS з `core.filemode=false`, у git-індексі немає біта виконання | `git update-index --chmod=+x steps/12_ci_cd/scripts/smoke.sh` |
| `ADMIN_PASSWORD: задай ADMIN_PASSWORD — той самий, з яким створено .env` | smoke запущено без змінної | `ADMIN_PASSWORD=… ./scripts/smoke.sh` з тим паролем, що й `make_env.py` |
| `.env уже є — не чіпаю`, код 1 | `make_env.py` не перезаписує існуючий `.env` | видали старий `.env` (якщо він лише для smoke) або візьми пароль, з яким його створено |
| після `✓ nginx відповідає` — `json.decoder.JSONDecodeError: Expecting value` | пароль у `ADMIN_PASSWORD` не той, з яким створено `.env`: `/api/admin/token` відповів `401` з порожнім тілом для `curl -sf` | у журналі api — `POST /api/admin/token → 401`; задай правильний пароль або перегенеруй `.env` |
| `failed to create network …_edge: … Pool overlaps with other one on this address space` | інша мережа Docker на машині вже займає `172.28.0.0/…` (у `docker-compose.yml` — `subnet: 172.28.0.0/24`) | `docker network ls`, `docker network inspect`; прибери чужу мережу або в локальній копії зміни підмережу й `FORWARDED_ALLOW_IPS` разом |
| `test_runs_as_non_root_and_cannot_change_code`: `assert 0 != 0` | образ зібрано з копії, де всі файли `rwxrwxrwx` (наприклад, з `/mnt/c` у WSL) — код у образі може змінити будь-хто | збирай з git-клону на файловій системі Linux; у CI права файлів нормальні |
| `TypeError: Depends() got an unexpected keyword argument 'scope'` лише в `min-versions` | нижня межа FastAPI нижча за 0.121 | підніми межу в `requirements.txt` до версії, де з'явилось API |
| `FAILED: New upgrade operations detected: [('add_column', …)]` у job `postgres`, а тести зелені | змінено `tables.py` без міграції | `alembic revision --autogenerate -m "…"`, перечитати міграцію |
| `✗ база й Redis без портів назовні: … отримали 127.0.0.1:…->5432/tcp` | у `docker-compose.yml` для `postgres` / `redis` додано `ports` | порти бази — лише в `docker-compose.dev.yml` (крок 11), не в основному файлі |

## Практика { #practice }

### Розібраний приклад: бейдж статусу в README { #worked-example }

Задача: щоб статус CI було видно не лише в PR, а й на головній сторінці репозиторію.

1. **Звідки статус.** GitHub віддає SVG-бейдж для кожного workflow; адреса складається з імені файлу workflow: `…/actions/workflows/<файл>.yml/badge.svg`.
2. **Яка гілка.** За замовчуванням бейдж показує статус останнього прогону на гілці за замовчуванням (`main`); `?branch=…` — іншої гілки.
3. **Куди клікати.** Бейдж — посилання на сторінку workflow, де видно всі прогони.

```markdown
[![news_hub — CI/CD](https://github.com/NikoriakViktor/news_hub/actions/workflows/news_hub.yml/badge.svg)](https://github.com/NikoriakViktor/news_hub/actions/workflows/news_hub.yml)
```

Бейдж має сенс лише після першого завершеного прогону в `main`: доки прогонів немає, показувати нічого. І він показує статус **останнього** прогону: якщо push у `main` змінив лише `docs/`, workflow не запустився і бейдж показує попередній результат.

### Зміни приклад { #modify }

1. У копії `news_hub.yml` поверни тригер Django-книги: `pull_request: branches: [main]`. Що буде з PR, відкритим поверх іншого PR (base — гілка `feature-a`)?
2. У `requirements.txt` знизь межу до `fastapi>=0.115`. Який job почервоніє і з якою помилкою? Що покажуть інші jobs?
3. У `docker-compose.yml` додай `postgres` рядок `ports: ["127.0.0.1:55452:5432"]` і запусти `./scripts/smoke.sh`.

??? success "Що покаже запуск"

    1. Workflow не запуститься зовсім (скрипт з [розділу 1](triggers.md#result): `pull_request  feature-a  …  ні`). У PR не буде ні галочки, ні хрестика — і його можна злити без перевірки.
    2. `pytest · мінімальні версії (Python 3.10)`: `uv` ставить `fastapi==0.115.0`, і збір тестів падає на `news_hub/api.py:185` з `TypeError: Depends() got an unexpected keyword argument 'scope'`. Решта jobs зелені: вони ставлять найновішу FastAPI.
    3. Шість перевірок зелені, сьома — `✗ база й Redis без портів назовні: очікували , отримали 127.0.0.1:55452->5432/tcp`; далі `docker compose ps -a` і журнали, потім `down -v`. Код виходу 1 — job `docker` червоний, `publish` не запуститься.

### Спробуй самостійно: покриття як артефакт { #coverage-artifact }

Додай до job `tests` покриття: `pytest --cov=news_hub --cov-report=xml` і збережи `coverage.xml` дією `actions/upload-artifact@v4`.

**Критерії перевірки:**

- повний набір тестів проходить **один** раз (не `pytest` і ще окремо `pytest --cov`);
- артефакт — лише з одного варіанта matrix (`if: matrix.python == '3.13'`);
- у вкладці Summary прогону з'являється артефакт `coverage-xml`;
- `.coveragerc` кроку підхоплюється: у звіті є гілки (`branch = true`), а рядки async SQLAlchemy видно (`concurrency = thread,greenlet`);
- `actions/upload-artifact` не потребує додаткових `permissions`: `contents: read` досить.

### Знайди помилку { #find-bug }

Workflow для `news_hub`. На PR він зелений.

```yaml
on:
  push:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    env:
      GEMINI_API_KEY: AIzaSyD-demo-key-not-real-0000000000000
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with: {python-version: "3.13"}
      - run: pip install -r steps/12_ci_cd/requirements.txt
      - run: cd steps/12_ci_cd && pytest || true
```

Знайди чотири проблеми.

??? success "Відповідь"

    1. **`pytest || true`** — `|| true` робить код виходу кроку нульовим за будь-якого результату ([перевірено](what_to_check.md#or-true)). Тести можуть падати скільки завгодно, CI зелений. Зелений CI, що нічого не перевіряє, гірший за відсутній: йому вірять.
    2. **`requirements.txt` замість `requirements-dev.txt`** — pytest, fakeredis, pytest-asyncio не встановлені; `pytest` падає з `command not found`, і `|| true` ховає й це.
    3. **Ключ у файлі workflow** — він у git назавжди, і його бачить кожен, хто бачить репозиторій. Справжній ключ — у Secrets (`${{ secrets.GEMINI_API_KEY }}`); для тестів він не потрібен зовсім (FakeLLM, крок 7).
    4. **Тригери** — `push` без гілок запускає workflow на кожен push у будь-яку гілку (разом з `pull_request` — двічі на коміт), а `pull_request: branches: [main]` пропускає PR у інші гілки. І немає `paths`: зміна в книзі теж запускає тести.

    Бонус: немає `permissions` (токен з правами за замовчуванням репозиторію), `timeout-minutes` і `cache: pip`.

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| workflow, job, step | файл у `.github/workflows/`; job — окрема чиста VM; step — `uses` або `run`, зелений при коді виходу `0` |
| тригери | `pull_request` без `branches` + `paths` (і сам workflow в `paths`); `push` — лише `main`; `workflow_dispatch` — ручний запуск |
| `concurrency` | новий прогін у тій самій групі скасовує старий |
| тести | без ручного списку — pytest знаходить сам; один повний прогін; без `|| true` |
| середовища | matrix версій Python; мінімальні версії (`uv --resolution lowest-direct`); PostgreSQL і Redis у `services` з healthcheck |
| схема бази | `alembic upgrade head` + `alembic check` — модель без міграції не пройде |
| система | тести образу + smoke стеку через nginx — те, чого не бачать тести коду |
| порядок | jobs паралельно; `needs` — лише де справді треба чекати; `fail-fast: false`; `timeout-minutes` |
| права | `permissions: contents: read`; `packages: write` — лише `publish`; job-рівень замінює workflow-рівень |
| секрети | у Secrets, не у файлі; згенеровані в прогоні — `::add-mask::`, між кроками — `$GITHUB_ENV` |
| CD | образ `ghcr.io/<власник>/<репозиторій>/news_hub` з тегами `sha-…` і `latest` з `main`; деплой — окремий, свідомий крок |

## Самоперевірка { #self-check }

1. Чому відсутній прогін CI небезпечніший за червоний?
2. PR відкрито в гілку іншого PR. Запуститься `news_hub.yml`? А workflow Django-книги з `pull_request: branches: [main, master]`?
3. Що перевіряє job з мінімальними версіями, чого не перевіряє звичайний?
4. Чому тести зелені, а `alembic check` червоний, якщо додати колонку в `tables.py` без міграції?
5. Навіщо `needs: tests` у job з образом, якщо jobs можна запускати паралельно?
6. Звідки `publish` бере право писати в ghcr.io і чому це право не в усього workflow?
7. Що зробить `echo "::add-mask::$password"` і навіщо після нього `>> "$GITHUB_ENV"`?
8. Чи публікує `publish` той самий образ, що пройшов smoke?

??? success "Відповіді"

    1. Червоний видно — його виправлять. Відсутній виглядає як «усе гаразд»: PR зливають без жодної перевірки.
    2. `news_hub.yml` — так, у `pull_request` немає `branches`. Django-книги — ні: `branches` — це base PR, а base тут не `main` і не `master`.
    3. Що нижні межі в `requirements.txt` правдиві. Звичайний job ставить найновіші версії; з межею `fastapi>=0.115` лише `min-versions` падає з `TypeError: Depends() got an unexpected keyword argument 'scope'`.
    4. Тестові бази створюються з моделей (`Base.metadata.create_all`), тож колонка в них є. `alembic check` порівнює моделі зі схемою після міграцій — і бачить `add_column`, якого міграції не роблять. У продакшні схему робить саме Alembic.
    5. Щоб не витрачати найдовший job на образ і smoke, якщо код уже не пройшов тести, — і щоб у PR була одна червона причина, а не лавина наслідків (`docker` стає `skipped`).
    6. З `GITHUB_TOKEN` цього прогону з `permissions: packages: write` лише в job `publish`, який іде лише на push у `main`. Решта jobs запускають код з PR — їм досить читати. Писати токен може лише в пакети свого репозиторію — тому в імені образу є `${{ github.repository }}`.
    7. Далі в журналі job це значення замінюється на `***`, навіть якщо якась команда його надрукує. `$GITHUB_ENV` передає змінну наступним крокам job: кожен `run:` — окрема оболонка, а `smoke.sh` потрібен `ADMIN_PASSWORD`.
    8. Ні: з того самого коміту, але зібраний заново на іншій машині. `Dockerfile` той самий, версії пакетів визначаються в момент збірки.

## Що далі { #next }

Zero to Hero закінчено: `steps/12_ci_cd` — фінальна версія `news_hub`.

- [News Hub Deep Dive](../../deep_dive/README.md) — як фінальна версія влаштована зараз: архітектура, карта модулів, життєвий цикл запиту, модель даних і міграції, карта тестів, CI.
- [Практика](../../labs/README.md) — лабораторні до кожного кроку й фінальна лаба: пошуковий індекс `pg_trgm` і міграція 0005 на `steps/12_ci_cd`. Нова міграція — саме те, що перевірить `alembic check` у CI.

Попередній крок — [Крок 11. Docker Compose і деплой](../11_compose_deploy/index.md).
