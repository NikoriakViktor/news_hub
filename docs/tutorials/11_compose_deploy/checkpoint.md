# Контрольна точка: крок 11

## Перевір, що крок робочий { #check }

З папки `steps/11_compose_deploy`:

```text
$ pytest -q -p no:cacheprovider
........................................................................ [ 20%]
…
.......................................................                  [100%]
343 passed, 8 deselected in 33.86s
$ mypy --strict news_hub
Success: no issues found in 26 source files
```

Порівняно з кроком 10 (340 тестів) додалось 3:

| Де | Що перевіряє |
|---|---|
| `tests/unit/test_security.py::test_truncated_hash_fails_at_startup` | обрізаний хеш (як після підстановки Compose) → `RuntimeError` при старті, повний — проходить |
| `tests/integration/test_telegram_webhook.py::test_api_starts_while_telegram_is_down` | Telegram недоступний → API стартує, реєстрація повторюється й завершується, коли «Telegram» з'явився |
| `tests/integration/test_telegram_webhook.py::test_wrong_token_does_not_stop_api` | неправильний токен (401) → бот вимкнено, API працює |

8 deselected — тести з маркерами `llm` (справжні виклики моделі) і `docker` (збірка образу, крок 10): вони запускаються лише явно, `pytest -m llm` / `pytest -m docker`. Для цієї сторінки `pytest -m docker` не запускався.

Сам стек — порядок запуску, nginx і IP клієнта, `.env`, Telegram, оновлення, копії, бекап — перевірено наживо командами з розділів кроку. Частина цього в [кроці 12](../12_ci_cd/index.md) переїде в CI.

## Чекліст { #checklist }

- [ ] `cp .env.example .env` без заповнення → `docker compose config` падає з «задай POSTGRES_PASSWORD у .env».
- [ ] `docker compose up -d --build --wait` повертає 0; у `docker compose ps` чотири сервіси `(healthy)`, `migrate` — `Exited (0)`.
- [ ] `curl localhost/health/ready` → `{"status":"ok","checks":{"database":"ok","redis":"ok"}}`.
- [ ] Назовні відкритий лише порт nginx: у `ps` в `api`, `postgres`, `redis` — порт без `0.0.0.0:…->`.
- [ ] 7 невдалих входів з вигаданим `X-Forwarded-For` → `401 ×5, 429 ×2`; у Redis один ключ `rate:login:<твоя адреса>`.
- [ ] Хеш без лапок у `.env` → `api` не стартує з `RuntimeError … в одинарних лапках`.
- [ ] Бот з `TELEGRAM_API_URL=http://twin:8081`, але без `--profile twin` → `api` healthy, у журналі `Telegram недоступний … повтор через …`.
- [ ] `./scripts/backup.sh` → `DELETE /api/news` → `./scripts/restore.sh …` → `count` знову 168.
- [ ] Можеш пояснити, навіщо nginx перезаписує `X-Forwarded-For`, якщо uvicorn і так вірить лише nginx.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `failed to create network …_edge: … invalid pool request: Pool overlaps with other one on this address space` | на машині вже є мережа Docker, що перетинає `172.28.0.0/24` (тут була `172.28.0.0/16` іншого проєкту) | знайти: `docker network inspect $(docker network ls -q) --format '{{.Name}} {{range .IPAM.Config}}{{.Subnet}}{{end}}'`; змінити `subnet`, `ipv4_address` і `FORWARDED_ALLOW_IPS` разом (усі три — одна адреса nginx) |
| `required variable POSTGRES_PASSWORD is missing a value: задай POSTGRES_PASSWORD у .env` | `.env` немає або пароль порожній | `cp .env.example .env` і заповнити |
| `The "pVoAkKpIgbdK5I" variable is not set. Defaulting to a blank string.` | значення з `$` у `.env` без лапок | одинарні лапки: `ADMIN_PASSWORD_HASH='$2b$12$…'` |
| `container …-api-1 is unhealthy`, у `logs api` — `RuntimeError: ADMIN_PASSWORD_HASH …` | хеш обрізаний (див. попередній рядок) або там пароль, а не хеш | `python -m news_hub.security`, рядки — як надруковано |
| `service "migrate" didn't complete successfully: exit 255` | міграція впала: `docker compose logs migrate` | виправити міграцію; API без неї свідомо не стартує |
| `Bind for 0.0.0.0:80 failed: port is already allocated` | порт 80 зайнятий іншим сервером | `HTTP_PORT=8080` у `.env` |
| nginx перші секунди відповідає `502` | `depends_on` без `condition` (`service_started`) | `condition: service_healthy` |
| у Redis лише `rate:login:<адреса nginx>`, усі клієнти ділять ліміт | uvicorn не вірить `X-Forwarded-For` від nginx: `FORWARDED_ALLOW_IPS` не збігається з `ipv4_address` nginx | одна й та сама адреса в обох місцях |
| `{"status":"unavailable","checks":{"database":"ConnectionRefusedError",…}}` при `(healthy)` у `ps` | `localhost` у `DATABASE_URL` усередині контейнера — це сам контейнер | ім'я сервісу: `@postgres:5432` |
| нова копія `api` після `--scale` не отримує запитів | nginx визначив адреси `api` при старті | `docker compose exec nginx nginx -s reload` |
| `./scripts/backup.sh`: `service "postgres" is not running`, хоча стек працює | стек запущено з `-p <ім'я>`, а скрипт шукає проєкт `news_hub` | `COMPOSE_PROJECT_NAME=<ім'я> ./scripts/backup.sh` |

## Практика { #practice }

### Розібраний приклад: дві копії API і один ліміт { #worked-example }

Задача: запустити `api` у двох копіях і переконатися, що rate limit входу не подвоївся.

1. **Де живе стан.** Ліміти, кеш і статуси задач — у Redis (крок 4), не в пам'яті процесу. Отже, копії можна запускати без змін у коді.
2. **Чи немає гонки при старті.** Міграції — сервіс `migrate`, один раз ([розділ 1](startup_order.md#release)). `--scale api=2` міграцій не дублює.
3. **Чи побачить nginx нову копію.** Ні, поки не перечитає конфігурацію: адреси `api` він визначив при старті.
4. **Перевірка.** 12 невдалих входів: якщо ліміт спільний — `429` з шостої спроби, незалежно від того, яка копія відповідала.

```bash
docker compose up -d --scale api=2 --wait
docker compose exec nginx nginx -s reload
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code} " -X POST localhost/api/admin/token \
    -H 'Content-Type: application/json' -d '{"username":"admin","password":"guess'$i'"}'; done
```

```text
 Container newshub-step11-bookcheck-api-1  Healthy
 Container newshub-step11-bookcheck-api-2  Healthy
401 401 401 401 401 429 429 429 429 429 429 429
api-1: 6, api-2: 6
rate:login:10.28.0.1
```

Запити розійшлися порівну, ліміт — один. Докладно, з тим, що було до `nginx -s reload`, — [Деплой: кілька копій API](deploy.md#replicas).

### Зміни приклад { #modify }

1. Задай для `api` `FORWARDED_ALLOW_IPS: 127.0.0.1` (значення uvicorn за замовчуванням). Який ключ з'явиться в Redis після спроби входу?
2. У `nginx.conf` заміни `$remote_addr` у `X-Forwarded-For` на `$proxy_add_x_forwarded_for`, `FORWARDED_ALLOW_IPS` не чіпай. Чи обійде клієнт ліміт вигаданим заголовком? А якщо ще й `FORWARDED_ALLOW_IPS: "*"`?

??? success "Що показав запуск"

    1. `rate:login:10.28.0.10` — адреса nginx (у підмережі кроку — `172.28.0.10`): заголовку від нього uvicorn
       більше не вірить, і всі клієнти знову «одна людина».
    2. З довірою лише nginx — ні: `401 ×5, 429 ×2`, ключ — справжня адреса (uvicorn 0.54 бере крайню праву
       адресу, якій не довіряє). З `"*"` — так: 8 спроб, 8 ключів `rate:login:10.66.0.1…8`, жодного `429`.
       Деталі — [Два шари](nginx_real_ip.md#two-layers).

### Спробуй самостійно: бекап за розкладом у Compose { #backup-service }

Додай сервіс `backup` з профілем `backup`: образ `postgres:16-alpine`, кожні N секунд (для перевірки; на сервері — раз на добу) робить `pg_dump | gzip` у том `backups` і зберігає останні 7 файлів.

**Критерії перевірки:**

- пароль бази — з `.env`, не в `docker-compose.yml`;
- `set -euo pipefail`: недоступна база — жодного порожнього файлу;
- `./scripts/restore.sh` відновлює базу з файлу, зробленого сервісом;
- без `--profile backup` сервіс не запускається, з ним — чекає `postgres` healthy.

### Знайди помилку { #find-bug }

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: news_hub
      POSTGRES_USER: news
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
  api:
    image: news_hub:11
    environment:
      DATABASE_URL: postgresql+asyncpg://news:${POSTGRES_PASSWORD}@localhost:5432/news_hub
      REDIS_URL: redis://redis:6379/0
    ports:
      - "8080:8000"
    depends_on: [db, redis]
  redis:
    image: redis:7-alpine
```

```text
$ docker compose up -d && sleep 40 && docker compose ps
SERVICE   STATUS                    PORTS
api       Up 42 seconds (healthy)   0.0.0.0:8080->8000/tcp, [::]:8080->8000/tcp
db        Up 42 seconds             0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
redis     Up 42 seconds             6379/tcp
$ curl localhost:8080/health/ready
{"status":"unavailable","checks":{"database":"ConnectionRefusedError","redis":"ok"}}
```

`docker compose ps` каже «healthy». Що не так? Знайди три проблеми.

??? success "Відповідь"

    1. **`localhost` у `DATABASE_URL`.** У контейнері `api` `localhost` — сам `api`, бази там немає:
       `ConnectionRefusedError`. Адреса — ім'я сервісу: `@db:5432`.
    2. **Порт бази відкритий усьому світу.** `"5432:5432"` — це `0.0.0.0:5432` (видно в `ps`), і на сервері
       Docker пропускає його в обхід ufw. Для `api` цей порт не потрібен: вони в одній мережі. Для розробки —
       `127.0.0.1:5432:5432` в окремому файлі, як `docker-compose.dev.yml`.
    3. **`depends_on` без умов і без міграцій.** `api` стартує, щойно контейнер `db` запущений, а не готовий,
       і таблиць ніхто не створює. Потрібні healthcheck у `db`, `condition: service_healthy` і окремий `migrate`
       з `service_completed_successfully`.

    А «healthy» — бо HEALTHCHECK образу питає `/health` (процес живий), і це правда: `curl localhost:8080/health`
    → `{"status":"ok"}`. Готовність до роботи показує `/health/ready` — саме її в кроці перевіряє healthcheck `api`.

    Бонус: `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}` без `:?` — забутий `.env` дасть лише попередження й порожній
    пароль, а не помилку.

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| `depends_on` | лише з `condition`: `service_healthy`, `service_completed_successfully` |
| healthcheck | інструментом, що є в образі; для API в Compose — готовність (`/health/ready`); `disable: true` для ролей без сервера |
| випуск і робота | міграції — окремий одноразовий сервіс `migrate`; `api` — скільки завгодно копій |
| `x-app: &app`, `<<: *app` | спільна частина сервісів одного образу — один раз |
| nginx | `X-Forwarded-For $remote_addr` + `FORWARDED_ALLOW_IPS` = адреса nginx; `Host $http_host`; `/nginx-health` |
| мережі й порти | назовні — лише nginx; база й Redis — без `ports`; Docker обходить ufw; dev-порти — `127.0.0.1` в окремому файлі |
| `.env` | поза git; значення з `$` — в одинарних лапках; `${VAR:?…}` — обов'язкові; повний формат перевіряється при старті |
| зовнішні сервіси | Telegram, LLM недоступні → API однаково стартує; реєстрація — у фоні з повторами |
| оновлення | `git pull && docker compose up -d --build --wait`: перезапускається лише змінене; простій — секунди |
| бекап | `pg_dump` з `pipefail` і тимчасовим файлом; перевіряй відновленням; копія — на інший сервер |

## Самоперевірка { #self-check }

1. Чим `depends_on: [api]` відрізняється від `condition: service_healthy`?
2. Чому міграції — окремий сервіс, а не перший рядок команди `api`?
3. Навіщо nginx перезаписує `X-Forwarded-For`, якщо uvicorn і так вірить лише nginx?
4. У `.env` без лапок `ADMIN_PASSWORD_HASH=$2b$12$abc…`. Що отримає застосунок і що він зробить?
5. Чому `migrate` і `bot` у Compose мають `healthcheck: disable: true`?
6. Telegram недоступний при старті. Що буде з API у кроці 10 і в кроці 11?
7. Що перевірити після кожного бекапу?

??? success "Відповіді"

    1. Список — це `service_started`: чекає, поки контейнер **запуститься** (API ще не відповідає, nginx віддає
       `502` — у перевірці ~6 с). `service_healthy` — поки healthcheck поверне успіх.
    2. Кілька копій `api` одночасно запускали б ті самі міграції й конфліктували. Випуск — один раз
       (`service_completed_successfully`), робота — у N копіях. І впали міграції — `api` не стартує зовсім.
    3. Довіра лише nginx закриває обхід напряму (хтось у мережі звертається до `api:8000` з вигаданим
       заголовком). Перезапис гарантує, що до API доходить одна адреса — та, яку бачив nginx, — незалежно від
       того, як інший читач заголовка (журнал, інший сервер, інша версія uvicorn) розбирає список. Uvicorn 0.54 з
       довірою лише nginx і з дописаним списком теж бере правильну адресу, але з `"*"` дописаний список — це обхід.
    4. Compose підставить порожнечу замість `$abc…` (до першого `.` чи `/`) з попередженням `variable is not set`.
       Застосунок отримає обрізаний хеш, `BCRYPT_HASH.fullmatch` не пройде — `RuntimeError` при старті, `api`
       unhealthy. У кроці 10 (перевірка «починається з `$2`») застосунок стартував, а вхід відповідав `500`.
    5. HEALTHCHECK образу питає `:8000/health`, а вони сервера не запускають — були б «unhealthy» завжди, і
       `up --wait` падав би.
    6. Крок 10: `TelegramNetworkError` у `lifespan` → «Application startup failed» → перезапуск по колу, новини
       недоступні. Крок 11: `api` healthy, реєстрація — фонова задача з паузами 1, 2, 5, 10, 30 с; з'явився
       Telegram — `бот зареєстрований (спроба N)`. Неправильний токен — один `ERROR`, API працює.
    7. Що з нього відновлюється: `restore.sh` на копії стеку й перевірка даних (`count`). Плюс копія файлу на інший
       сервер.

## Що далі { #next }

[Крок 12. CI/CD на GitHub Actions](../12_ci_cd/index.md) — тести на кількох версіях Python, `mypy --strict`, збірка образу й перевірка `/health/ready` у CI на кожен pull request, публікація образу.
