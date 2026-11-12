# Контрольна точка: крок 10

## Перевір, що крок робочий { #check }

З папки `steps/10_docker`:

```text
$ pip install -r requirements-dev.txt
$ pytest -q -p no:cacheprovider
........................................................................ [ 20%]
…
....................................................                     [100%]
360 passed, 8 deselected in 27.60s
$ mypy --strict news_hub
Success: no issues found in 26 source files
```

Порівняно з кроком 9 (355 тестів) додалось 5: три для `/health/ready` (`tests/integration/test_health.py`) і два для `env_lines` — з лапками й без. `8 deselected` — 2 тести `llm` і 6 тестів `docker`: `pytest.ini` вимикає їх за замовчуванням (`addopts = -m "not llm and not docker"`).

Образ — теж код, і його перевіряють тестами:

```text
$ pytest -m docker -q -p no:cacheprovider
......                                                                   [100%]
6 passed, 362 deselected in 28.43s
```

`tests/docker/test_image.py` збирає образ з копії проєкту, куди навмисно покладено те, що в образ потрапити не має права: `.env` з «секретом», `.venv`, файл бази, `__pycache__` у `news_hub/`. Далі — справжні `docker run` і `docker stop`. Без Docker тести пропускаються (`skipif`, «немає Docker»).

| Тест | Що перевіряє |
|---|---|
| `test_local_files_are_not_in_the_image` | `.env`, `.venv`, `tests`, `news_hub.db`, `requirements-dev.txt` немає в `/app`; `__pycache__` і `*.pyc` — ні в корені, ні в підпапках; «секрету» немає в `docker history --no-trunc` |
| `test_dev_dependencies_are_not_installed` | `import pytest` / `mypy` / `fakeredis` в образі падає |
| `test_runs_as_non_root_and_cannot_change_code` | UID 10001; `touch /app/news_hub/api.py` не вдається, `touch /data/probe` — вдається |
| `test_healthcheck_reports_healthy` | статус контейнера стає `healthy` (з `--health-interval=1s`) |
| `test_docker_stop_is_graceful` | `docker stop -t 10` — менше 8 с, код 0, `Application shutdown complete` у журналі |
| `test_migrations_run_on_a_volume` | `alembic upgrade head` у контейнері на томі → `alembic current` показує `(head)` |

Кожна поломка `Dockerfile` — shell-форма `CMD`, без `USER app`, без `.env` у `.dockerignore`, `HEALTHCHECK` на інший порт — червонить принаймні один тест.

!!! warning "Збірка з диска Windows у WSL"
    Запущені з `/mnt/c/…` тести образу дали `1 failed, 5 passed`: впав `test_runs_as_non_root_and_cannot_change_code`, бо файли на цьому диску мають права `777`, і `COPY` переносить їх в образ ([докладніше](user_data_env.md#user)). З `git clone` у файлову систему Linux — `6 passed`.

## Чекліст { #checklist }

- [ ] `docker build -t news_hub:10 .` збирається; `docker images news_hub:10` — сотні МБ, а не гігабайти.
- [ ] `docker run --rm news_hub:10 ls -A /app` — лише `alembic.ini`, `data`, `migrations`, `news_hub`, `requirements.txt`.
- [ ] Після зміни одного `.py` перезбирання — секунди, усі кроки до `COPY . .` — `CACHED`.
- [ ] `docker run --rm news_hub:10 whoami` → `app`; `touch /app/news_hub/api.py` → `Permission denied`.
- [ ] Новини, зібрані в одному контейнері, видно в новому контейнері з тим самим томом.
- [ ] Без мережі `news` `/health/ready` → `503` з `"redis":"ConnectionError"`, а `/health` → `200`.
- [ ] `docker ps` показує `(healthy)`.
- [ ] `docker stop -t 10 api` — 1–2 с, `ExitCode` 0, у журналі `Application shutdown complete`.
- [ ] `pytest -m docker` — `6 passed`.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `docker run … cat /app/.env` показує ключі | `.env` не в `.dockerignore` | додати `.env` і `.env.*`; перезібрати; ключі, що вже потрапили в образ, — замінити |
| образ на гігабайт, `COPY . .` — сотні МБ | у контекст потрапив `.venv` | `.venv/` у `.dockerignore` |
| `__pycache__` в образі, хоча він в `.dockerignore` | шаблон `__pycache__` — лише в корені контексту | `**/__pycache__`, `**/*.py[cod]` |
| перезбирання щоразу ставить усі залежності | `COPY . .` перед `pip install` | спершу `COPY requirements.txt .` + `pip install`, потім `COPY . .` |
| `(sqlite3.OperationalError) unable to open database file` при `alembic upgrade head` | база в `/app`, а `app` там писати не може | `DATABASE_URL` на `/data` і `-v news_data:/data` |
| `/health/ready` → `"redis":"ConnectionError"`, у журналі `connecting to localhost:6379` | `localhost` у контейнері — сам контейнер | `--network news` і `REDIS_URL=redis://redis:6379/0` |
| `curl localhost:8000` з комп'ютера — `Connection refused` | немає `-p 8000:8000` або uvicorn слухає `127.0.0.1` | `-p 8000:8000`; `--host 0.0.0.0` (у `CMD` кроку вже так) |
| `Exited (3)`, `RuntimeError: ADMIN_PASSWORD_HASH — bcrypt-хеш …` | у `--env-file` значення в лапках | `python -m news_hub.security --env-file` — рядки без лапок |
| `docker stop` триває 10 с, `exit 137` | shell-форма `CMD`: `SIGTERM` отримує `/bin/sh` | exec-форма: `CMD ["uvicorn", …]` |
| `exit 137` за 1–2 с, хоча в журналі `Finished server process` | на машині менший час очікування `docker stop` | `docker stop -t 10`; перевір `docker inspect -f '{{.Config.StopTimeout}}'` |
| `test_runs_as_non_root_and_cannot_change_code` червоний у WSL | файли з `/mnt/c` мають права `777` | збирати з копії в Linux-папці |

## Практика { #practice }

### Розібраний приклад: бот з того самого образу { #worked-example }

Задача: запустити Telegram-бота в режимі polling ([крок 9](../09_telegram_bot/index.md)) у контейнері. Без справжнього Telegram — проти двійника Telegram Bot API на своєму комп'ютері.

1. **Новий образ не потрібен.** Бот — інший процес того самого застосунку: перевизначаємо команду після імені образу.
2. **Двійник — на комп'ютері, бот — у контейнері.** Ім'я комп'ютера зсередини контейнера — `host.docker.internal`; двійник має слухати `0.0.0.0`, а не лише `127.0.0.1`.
3. **Redis і база — ті самі, що в API**: мережа `news`, том `news_data`.

```bash
python -m tests.telegram_twin --host 0.0.0.0 --port 8081     # «Telegram» на твоєму комп'ютері

docker run -d --name bot --network news -v news_data:/data \
    --add-host host.docker.internal:host-gateway \
    -e REDIS_URL=redis://redis:6379/0 \
    -e BOT_TOKEN=123456:TEST-TOKEN -e TELEGRAM_API_URL=http://host.docker.internal:8081 \
    news_hub:10 python -m news_hub.bot

curl -X POST localhost:8081/_twin/say -d '{"text": "/news 3", "chat_id": 1001}'
curl 'localhost:8081/_twin/sent?chat_id=1001'
```

```text
$ docker logs bot
2026-11-11 21:28:30,606 INFO aiogram.dispatcher: Run polling for bot @news_hub_bot id=123456 - 'news_hub'
2026-11-11 21:28:38,701 INFO aiogram.event: Update id=1 is handled. Duration 29 ms by bot id=123456

відповідь бота (з /_twin/sent):
📰 <b>Останні новини</b> (3)

• <a href="https://www.rbc.ua/ukr/news/katar-vryatue-peregovori-ssha-ta-iranu-vens-1778281213.html">Катар спасет переговоры США и Ирана? Вэнс встретился с главным посредником</a> <i>Новини</i>
• …
```

Три деталі, кожна — з цього кроку:

- `host.docker.internal` — ім'я твого комп'ютера зсередини контейнера (`localhost` був би сам контейнер). На Linux його додає `--add-host …:host-gateway`, Docker Desktop — сам;
- двійник слухає `0.0.0.0`: на `127.0.0.1` його бачить лише сам комп'ютер. Для цього в кроці 10 у двійника з'явилась опція `--host`;
- новини — ті самі, що зібрав API: обидва контейнери бачать том `news_data`. Для SQLite це прийнятно лише для перевірки на одній машині: два процеси, що пишуть в один файл, заважають одне одному. У [кроці 11](../11_compose_deploy/index.md) обидва ходять у PostgreSQL.

### Зміни приклад { #modify }

1. Запусти бота **без** `--network news`. Що покаже `docker logs bot`, коли прийде повідомлення?
2. Запусти API з `-e WEB_CONCURRENCY=2`. Скільки процесів покаже `docker top api`?

??? success "Що покаже запуск"

    1. Бот стартує (`Run polling for bot @news_hub_bot`): до «Telegram» він ходить через `host.docker.internal`, а не через мережу `news`. Але на **кожне** повідомлення, навіть `/start`, у журналі:

        ```text
        ERROR aiogram.event: Cause exception while process update id=4 by bot id=123456
        ConnectionError: Error -2 connecting to redis:6379. Name or service not known.
        ```

        і двійник не отримує жодної відповіді (`/_twin/sent` → `[]`). Rate limit бота — outer middleware ([крок 9](../09_telegram_bot/index.md)): він звертається до Redis раніше за будь-який handler. Ім'я `redis` відоме лише в мережі `news`.
    2. Чотири процеси Python: головний uvicorn, `multiprocessing.resource_tracker` і два worker (`spawn_main`). Пам'ять — 535.9 МіБ проти 262.3 МіБ з одним процесом: кожен worker імпортує всі бібліотеки ([виміри](health_shutdown.md#workers)).

### Спробуй самостійно: образ на Python 3.13 { #python-313 }

Зроби версію Python параметром збірки:

```dockerfile
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim
```

**Критерії перевірки:**

- `docker build --build-arg PYTHON_VERSION=3.13 -t news_hub:10-py313 .` збирається;
- `docker run --rm news_hub:10-py313 python --version` → `Python 3.13.…`;
- `pytest -m docker` зелений для обох образів: фікстура `image` у `tests/docker/test_image.py` може брати версію зі змінної середовища й передавати `--build-arg`.

У [кроці 12](../12_ci_cd/index.md) CI проганяє тести на двох версіях Python матрицею; образ там збирається один — на `python:3.12-slim`. Цей параметр — шлях до того, щоб збирати матрицею й образ.

### Знайди помилку { #find-bug }

Dockerfile працює: образ збирається, `curl /health` відповідає `{"status":"ok"}`. Але в ньому три проблеми.

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10001 app
USER app
ENV GEMINI_API_KEY=AIzaSyD-book-demo-key-not-real-0000000
CMD uvicorn news_hub.api:app --host 0.0.0.0 --port 8000
```

Реальний вивід:

```text
$ echo "# x" >> news_hub/models.py && time docker build -q -t findbug .
real    0m37.690s

$ docker history findbug --no-trunc --format '{{.CreatedBy}}' | grep GEMINI
ENV GEMINI_API_KEY=AIzaSyD-book-demo-key-not-real-0000000

$ time docker stop -t 10 fb
real    0m10.276s
$ docker inspect -f '{{.State.ExitCode}}' fb
137
```

??? success "Відповідь"

    1. **`COPY . .` перед `pip install`.** Зміна будь-якого файлу інвалідує шар залежностей — 37.7 с на кожне перезбирання замість 1–2 с. Спершу `COPY requirements.txt .` і `pip install`, потім `COPY . .` ([Шари й кеш](layers_cache.md)).
    2. **Ключ в образі.** `ENV` у Dockerfile записується в метадані образу: `docker history` і `docker inspect` покажуть його кожному, хто має образ. Ключ — при запуску: `--env-file .env` чи `-e`, а в Compose — `env_file` / secrets.
    3. **Shell-форма `CMD`.** PID 1 — `/bin/sh`, він не передає `SIGTERM` uvicorn: `docker stop` чекає 10 с і вбиває (`137`), `lifespan` не виконується. Exec-форма: `CMD ["uvicorn", "news_hub.api:app", "--host", "0.0.0.0", "--port", "8000"]`.

    Бонус: без `.dockerignore` у `COPY . .` потрапить і `.env`, і `.venv`; без `ENV DATABASE_URL=…/data/…` SQLite спробує писати в `/app`, де `app` не має прав.

    `curl /health` нічого з цього не показує: усі проблеми — не в тому, **чи** працює застосунок, а в тому, як його збирають, що в ньому лежить і як він зупиняється. Тому образ перевіряють окремими тестами (`tests/docker/`).

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| образ / контейнер | рецепт і знімок / запущений процес; один образ — багато контейнерів і ролей (API, міграції, бот) |
| контекст і `.dockerignore` | в образ — лише потрібне для роботи; `.env`, `.venv`, тести, бази — ні; шаблони від кореня, `**/` — у будь-якій папці |
| `requirements.txt` / `requirements-dev.txt` | залежності роботи — в образ; pytest, mypy, fakeredis — лише локально й у CI |
| шари й кеш | від рідкісних змін до частих: базовий образ → залежності → код |
| секрети | лише при запуску; `ENV` у Dockerfile і `COPY .env` видно в образі назавжди |
| користувач | не root, фіксований UID 10001; код належить root, дані — користувачу |
| дані | том `/data`; контейнер можна видаляти будь-коли |
| мережа | `localhost` — сам контейнер; інші — за іменем у спільній мережі; слухати `0.0.0.0`; `-p` — для комп'ютера |
| `--env-file` | значення буквально, разом з лапками; `python -m news_hub.security --env-file` |
| здоров'я | `/health` — живий (`HEALTHCHECK`), `/health/ready` — готовий (база, Redis), `503` |
| зупинка | exec-форма `CMD`: PID 1 — застосунок, `SIGTERM` → `lifespan` → exit 0; shell-форма → 10 с і 137 |
| процеси | один на контейнер; більше — `WEB_CONCURRENCY` або кількість контейнерів |

## Самоперевірка { #self-check }

1. Чому `RUN rm .env` після `COPY . .` не прибирає секрет з образу?
2. Змінився лише `requirements.txt`. Які шари перезберуться, а які — з кешу?
3. Навіщо `/data` окремо, якщо контейнер і так має свою файлову систему?
4. Чим `/health` відрізняється від `/health/ready` і чому `HEALTHCHECK` питає саме `/health`?
5. Що означає код виходу 137 і як його уникнути?
6. Чому uvicorn у контейнері слухає `0.0.0.0`?
7. Чому `.env` з рядками `ADMIN_PASSWORD_HASH='$2b$…'` працює з `export`, але не з `docker run --env-file`?

??? success "Відповіді"

    1. Образ — стос шарів. `COPY` створив шар з `.env`, `RUN rm` — новий шар, де файлу немає, але попередній шар лишився в образі й дістається `docker save`.
    2. `FROM`, `ENV`, `WORKDIR` — з кешу; `COPY requirements.txt`, `RUN pip install` і все після них (`useradd`, `COPY . .`) — заново, бо попередній шар змінився.
    3. Файлова система контейнера зникає разом з ним, а в `/app` користувач `app` ще й писати не може. Том живе окремо: нова версія образу, новий контейнер — ті самі дані.
    4. `/health` — процес відповідає; `/health/ready` — ще й база з Redis доступні. Якби `HEALTHCHECK` питав про базу, падіння PostgreSQL робило б API «unhealthy» і (в оркестраторі) змушувало б його перезапускати — а перезапуск базу не полагодить.
    5. 128 + 9: процес убито `SIGKILL`, бо на `SIGTERM` за відведений час він не завершився. Найчастіше — shell-форма `CMD`: сигнал отримує `/bin/sh`, а не застосунок. Рідше — замалий час очікування `docker stop`.
    6. `127.0.0.1` усередині контейнера — сам контейнер; з'єднання ззовні (через `-p` чи з іншого контейнера) приходять на інший інтерфейс.
    7. Shell знімає лапки, і в змінній опиняється хеш. `--env-file` бере значення буквально: `'$2b$…'` з лапками — не bcrypt-хеш, `load_admin_settings` кидає `RuntimeError`, і застосунок не стартує (`Exited (3)`).

## Що далі { #next }

[Крок 11. Docker Compose і деплой](../11_compose_deploy/index.md) — мережа, том, порядок запуску (спершу база, потім міграції, потім API, коли `/health/ready` відповідає) і nginx — в одному `docker-compose.yml`; PostgreSQL замість SQLite; деплой на сервер.
