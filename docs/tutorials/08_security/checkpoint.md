# Контрольна точка: крок 8

## Перевір, що крок робочий { #check }

З папки `steps/08_security`:

```text
$ pytest -q -p no:cacheprovider
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 73%]
........................................................................ [ 97%]
......                                                                   [100%]
294 passed, 2 deselected in 8.18s
$ mypy --strict news_hub
Success: no issues found in 18 source files
```

Порівняно з кроком 7 (168 тестів) додалось 126 тестів безпеки: 67 unit (пароль, токени й лічильник входів, адреси, підписи й id доставки) і 59 integration (хто може писати, блокування входу, заголовки безпеки й `/docs`, SSRF на локальних серверах, webhook через API). Перелік — у [Тестах безпеки](security_tests.md#files).

## Чекліст { #checklist }

- [ ] `python -m news_hub.security` друкує `ADMIN_PASSWORD_HASH='$2b$12$…'` і `JWT_SECRET='…'`; обидва — в середовищі, в одинарних лапках.
- [ ] Без цих змінних `DELETE /api/news` → `503`, а `GET /api/news` → `200`.
- [ ] З `JWT_SECRET=change-me-in-production` uvicorn не стартує: `RuntimeError: JWT_SECRET має бути не коротшим за 32 символи`.
- [ ] `DELETE /api/news` без токена → `401` і заголовок `WWW-Authenticate: Bearer`; з токеном адміна → `200`.
- [ ] Шоста спроба входу з однієї адреси за 5 хвилин → `429` з `Retry-After`; двадцять перша невдача під тим самим ім'ям з будь-яких адрес → `429 … під цим іменем`, навіть з правильним паролем.
- [ ] Відповідь `POST /api/admin/token` має `Cache-Control: no-store`; будь-яка відповідь API — `X-Content-Type-Options: nosniff` і CSP `default-src 'none'`, `/docs` — без CSP.
- [ ] З `DOCS_ENABLED=false` `/docs`, `/redoc` і `/openapi.json` → `404`, а `GET /api/news` → `200`.
- [ ] У `/docs` є кнопка **Authorize**, 14 операцій з замком.
- [ ] `POST /api/sources` з `http://169.254.169.254/latest/meta-data/` → `400`; з `http://localhost/admin` → `201`, але `/fetch` → `400 … loopback`.
- [ ] Підписаний webhook → `202`; та сама доставка (`X-Webhook-Delivery`) удруге, навіть підписана заново, → `200` з тим самим `job_id`; змінене тіло чи id → `401`.
- [ ] Можеш пояснити, чому заміна `hmac.compare_digest` на `!=` і прибраний `run_in_threadpool` не валять жодного тесту.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `RuntimeError: ADMIN_PASSWORD_HASH — bcrypt-хеш ($2b$…), а не пароль` при старті | у змінній пароль, а не хеш; або хеш у **подвійних** лапках: shell підставив `$2`, `$12`, і з `"$2b$12$…"` лишилось `b2…` | `python -m news_hub.security`, хеш — в одинарних лапках: `export ADMIN_PASSWORD_HASH='$2b$12$…'` |
| `RuntimeError: JWT_SECRET має бути не коротшим за 32 символи` | короткий секрет або задано лише хеш без секрету | секрет з `python -m news_hub.security` (64 символи) |
| `503 адмін-доступ не налаштовано` | змінні задані в іншому терміналі чи після запуску uvicorn | `export …` у тому самому shell, потім перезапуск |
| `429 забагато запитів: 5 за 300 с` на правильний пароль | ліміт рахує **всі** спроби входу, і вдалі теж | зачекай `Retry-After` секунд; для розробки — `LOGIN_RATE_LIMIT` більше |
| `429 забагато невдалих входів під цим іменем` на правильний пароль | за 15 хв було 20 невдач під цим ім'ям — з будь-яких адрес (можливо, чужий підбір) | зачекай `Retry-After`; на розробці — `redis-cli DEL` ключа `login:fail:…` або менший `LOGIN_FAIL_WINDOW`; на сервері — подивись журнал: хто перебирав |
| Swagger на сервері → `404` | Compose задає `DOCS_ENABLED=false` (крок 11) | так і задумано; локально `DOCS_ENABLED` не задано — `/docs` працює |
| `401 токен прострочений` у Postman чи Swagger | токен живе `JWT_EXPIRE_MINUTES` (30) хвилин | новий вхід: запит «Вхід адміна → token» або Authorize ще раз |
| локальна RSS-стрічка `http://localhost:8080/rss` → `400 … порт 8080` чи `… loopback` | `safe_fetch` за замовчуванням ходить лише в публічний інтернет на 80/443 | у тестах — явна `FetchPolicy` через `dependency_overrides[get_fetch_policy]`, а не послаблення `DEFAULT_POLICY` |
| webhook → `401 підпис не збігається`, хоча секрет правильний | відправник підписав одні байти, а надіслав інші (`json.dumps` з іншими пробілами, `curl -d @file` з переносом рядка) | підписуй рівно ті байти, які надсилаєш |
| webhook → `401 запит старший за 300 с` | годинник відправника відстає чи спішить більше ніж на 5 хв, або запит підписали заздалегідь | синхронізуй час (NTP); підписуй перед самим надсиланням |
| webhook → `401 X-Webhook-Delivery: 8–64 символи …` | відправник не надіслав id доставки (старий відправник: підпис лише від часу й тіла) | id на кожну подію (`uuid4().hex`), підпис — від `"<час>.<id>." + тіло` |
| повтор webhook після збою мережі запустив другий збір | відправник при повторі генерує **новий** id доставки | id — один на подію: при повторі новий час і підпис, але той самий `X-Webhook-Delivery` |
| webhook → `409 ця доставка ще обробляється` | дві однакові доставки прийшли одночасно, перша ще не створила завдання | повтори пізніше — отримаєш `200` з `job_id` першої |

## Практика { #practice }

### Розібраний приклад: «хто я?» { #worked-example }

Задача: адмін-панелі потрібно знати, чий токен і коли він закінчиться, — щоб попередити «сесія закінчується». Ендпоінт `GET /api/admin/me`.

1. **Хто має доступ.** Лише адмін → `AdminDep`. Але `require_admin` нам потрібен ще й як **значення**: він повертає `sub`. Тому не `dependencies=[AdminDep]`, а параметр `username: Annotated[str, AdminDep]`.
2. **Звідки `exp`.** `require_admin` повертає лише ім'я, тож токен беремо ще раз з `bearer_scheme` і розбираємо `decode_token`. FastAPI кешує залежності в межах запиту, тож `bearer_scheme` не виконується двічі.
3. **Що повертаємо.** Модель `AdminMe`: ім'я і час закінчення в UTC.

```python title="news_hub/api.py (розв'язок)"
class AdminMe(BaseModel):
    username: str
    expires_at: datetime


@app.get("/api/admin/me", response_model=AdminMe, tags=["admin"])
async def admin_me(settings: AdminSettingsDep,
                   credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
                   username: Annotated[str, AdminDep]) -> AdminMe:
    """Хто я і до коли діє токен — для кнопки «Вийти» і попередження «сесія закінчується»."""
    assert credentials is not None                      # require_admin уже перевірив
    payload = decode_token(settings, credentials.credentials)
    return AdminMe(username=username, expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc))
```

```python title="tests/integration/test_admin_api.py (розв'язок)"
def test_admin_me(anon: TestClient) -> None:
    token = create_access_token(_settings(), "admin")
    me = anon.get("/api/admin/me", headers=_token_headers(token)).json()
    assert me["username"] == "admin"
    assert anon.get("/api/admin/me").status_code == 401
```

Запуск у копії кроку:

```text
{'username': 'admin', 'expires_at': '2026-11-11T21:44:55Z'}
401 {'detail': 'потрібен токен: Authorization: Bearer <access_token>'}
$ pytest -q tests/integration/test_admin_api.py
38 passed in 0.82s
$ pytest -q tests/integration/test_api.py
1 failed, 16 passed in 0.72s
$ mypy --strict news_hub
Success: no issues found in 18 source files
```

- **Тест захисту нічого не дописує.** `test_every_other_endpoint_requires_admin` знаходить `require_admin` у залежностях нового маршруту, а `test_anonymous_gets_401` сам додає для нього випадок: було 36 тестів у файлі — стало 38 (`test_admin_me` + `[GET-/api/admin/me]`). Якби `AdminDep` забули, перший тест показав би `('GET', '/api/admin/me')` у різниці множин.
- **Червоний `test_openapi_lists_endpoints`** — так і має бути: він перелічує всі шляхи API, і новий шлях `/api/admin/me` треба дописати в його множину. Це другий запобіжник: новий ендпоінт не з'явиться в API непомітно.

### Зміни приклад { #modify }

1. У фікстурі `local_policy` (`tests/integration/test_sources_ssrf.py`) додай `max_redirects=0` і запусти `pytest tests/integration/test_sources_ssrf.py`. Який тест впав і з яким повідомленням? Чому тести перенаправлень на внутрішній сервіс досі зелені?
2. У `verify_signature` заміни `hmac.compare_digest(...)` на `signature != sign(...)`. Скільки тестів впало?
3. У `claim_delivery` прибери `nx=True`. Які тести впали і що сталося б з повтором доставки в житті?

??? success "Що покаже запуск"

    1. Червоний один — `test_fetch_rss_source`:

        ```text
        E       AssertionError: {'detail': 'джерело недоступне: більше 0 перенаправлень'}
        FAILED tests/integration/test_sources_ssrf.py::test_fetch_rss_source - Assert...
        1 failed, 13 passed in 0.76s
        ```

        Стрічка доступна лише через `/moved → /rss`. Решта 13 зелені. Перенаправлення на внутрішній сервіс, метадані й `file://` зупиняє `check_url` **ще до** того, як цикл дійде до ліміту: адресу з `Location` перевіряють першою.

    2. Жодного: `294 passed, 2 deselected`. Результат порівняння той самий, різниться лише **час**: `!=` зупиняється на першому неспівпадінні. Функціональний тест такого не бачить. Тому правило записане в `CLAUDE.md` кроку і перевіряється на рецензії, а не тестом.

    3. Три — `3 failed, 291 passed`: `test_same_delivery_is_claimed_once` (unit) і обидва тести повтору в API, `test_exact_replay_returns_same_job` і `test_resent_delivery_with_new_signature_does_not_scrape_twice`. Без `NX` `SET` просто перезаписує ключ: кожен повтор «новий», і збір запускається стільки разів, скільки відправник повторив доставку.

### Спробуй самостійно: scraper через `FetchPolicy` { #try-yourself }

`scraper.py` (крок 2) завантажує сторінки rbc.ua через `aiohttp.ClientSession()` без resolver-перевірки і з автоматичними перенаправленнями. `ScrapeRequest.pages` приймає лише `is_rbc_host`, але якщо rbc.ua перенаправить на внутрішню адресу, aiohttp піде туди.

Зроби так, щоб `scrape_all_async` і `scrape_sequential` приймали `policy: FetchPolicy = DEFAULT_POLICY`, з'єднувались через `PolicyResolver` і перевіряли перенаправлення так само, як `safe_fetch`.

**Критерії перевірки:**

- тести `tests/integration/test_scraper_server.py` проходять з явною локальною політикою;
- новий тест: сторінка `302 → http://169.254.169.254/` дає `PageResult.error`, а не новини;
- до «внутрішнього» сервера — 0 запитів (як `HITS` у `test_sources_ssrf.py`);
- `mypy --strict news_hub` чистий.

### Знайди помилку { #find-bug }

Функція із захистом від SSRF і тест до неї (приклад з OWASP Top 10, A10; тест зелений):

```python
ALLOWED_HOSTS_FOR_FETCH = ['i.imgur.com', 'avatars.githubusercontent.com']

def is_safe_url(url):
    parsed = urlparse(url)
    return parsed.hostname in ALLOWED_HOSTS_FOR_FETCH

def upload_avatar(request):
    url = request.POST.get('avatar_url')
    if not is_safe_url(url):
        raise PermissionDenied
    response = requests.get(url)
    ...


def test_internal_url_rejected():
    assert not is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not is_safe_url("http://localhost:6379/")
    assert is_safe_url("https://i.imgur.com/cat.png")
```

Як отримати відповідь внутрішнього сервісу через `upload_avatar`? Вивід атаки на двох локальних серверах ([як це зроблено](ssrf.md#old)):

```text
is_safe_url: True
фінальна адреса: http://localhost:40349/latest/meta-data/
відповідь: INTERNAL: aws_secret_access_key=...
```

??? success "Відповідь"

    `is_safe_url` перевіряє **першу** адресу, а `requests.get` за замовчуванням іде за перенаправленнями: `302` з дозволеного хоста веде куди завгодно. Вистачить одного «відкритого перенаправлення» на дозволеному сайті (сторінки на кшталт `/redirect?to=…`), і захист обійдено. Тест перевіряв саму функцію на рядках, а не шлях запиту, тож був зелений.

    Виправлення в `safe_fetch`: `allow_redirects=False` і кожен `Location` — знову через `check_url` і resolver, який перевіряє IP **з'єднання**. Тест на це — `test_redirect_is_checked_again`: справжній aiohttp проти локального сервера, що перенаправляє, і лічильник запитів «внутрішнього» сервісу, який має лишитися нулем.

    Друга проблема — `requests.get(url)` без `timeout`: повільний сервер триматиме робітника вічно.

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| JWT адміна | HS256 у коді, `require: exp, sub, role`; `401` — не автентифікований, `403` — не має прав |
| Пароль | bcrypt-хеш у середовищі, перевірка — у пулі потоків; > 72 байт — «не той пароль»; одна відповідь на чуже ім'я і чужий пароль; 5 спроб за 300 с з адреси і 20 невдач за 900 с на ім'я |
| Налаштування | без значень за замовчуванням: не задано → `503`, задано погано → не стартує |
| Хто може писати | `dependencies=[AdminDep]` + тест, що обходить усі маршрути і порівнює з `PUBLIC` |
| SSRF | перевіряти IP **з'єднання** (resolver), а не рядок URL; кожне перенаправлення; порти, розмір, тип; відповідь не віддавати |
| Webhook | HMAC-SHA256("<час>.<id доставки>." + сирі байти тіла), вікно 300 с, `SET NX` на id доставки (повтор → `200`, те саме завдання), `compare_digest`, секрет не в URL |
| Заголовки й `/docs` | `nosniff`, `DENY`, `no-referrer`, CSP на JSON — чистим ASGI-middleware; токен — `no-store`; `DOCS_ENABLED=false` на сервері |
| Що ловлять тести | атаки — так (підроблені токени, адреси, повтори, перебір під одним ім'ям); час — ні (витік часу порівняння, блокування циклу подій): це рецензія |

## Самоперевірка { #self-check }

1. Чим `401` відрізняється від `403` у `require_admin`? Наведи запит для кожного.
2. Навіщо перевіряти пароль, коли ім'я вже неправильне?
3. Чому `JWT_ALGORITHM` — константа в коді, а не змінна середовища?
4. Чому `http://localhost/admin` пройшов `POST /api/sources`, але не пройшов `/fetch`? Чи не краще перевіряти DNS при додаванні?
5. Навіщо в підписі webhook час, якщо є `SET NX`? І навпаки?
6. Чому підпис рахують від сирих байтів, а не від `json.loads(body)`?
7. Який захист кроку жоден тест не перевіряє і чому?
8. Чому ключ повтору webhook — id доставки, а не підпис? І чому повтор відповідає `200`, а не `409`?
9. Ліміт на адресу вже є. Навіщо ще лічильник на ім'я — і яка в нього ціна?
10. Чому `SecurityHeadersMiddleware` — чистий ASGI, а не `@app.middleware("http")`, як решта?

??? success "Відповіді"

    1. `401` — ми не знаємо, хто це: токена немає, підпис не збігається, строк минув (`DELETE /api/news` без заголовка). `403` — знаємо, хто, але прав немає: справжній токен з `role: user`.
    2. Інакше чуже ім'я відповідає миттєво, а своє — після bcrypt (~0,23 с). Різниця в часі підказує, що ім'я вгадано, і далі треба перебирати лише паролі.
    3. Алгоритм визначає, **як** перевіряти підпис. Якщо його можна змінити ззовні (чи взяти з заголовка токена), атакувальник обере зручний: `none` без підпису або інший, де секрет використовується не так. `algorithms=["HS256"]` у `decode` приймає лише один.
    4. Ім'я без DNS не перевірити, а DNS можна змінити будь-коли після додавання. Перевірка при додаванні дала б хибну впевненість, тому IP перевіряє resolver при **кожному** з'єднанні.
    5. `SET NX` без часу мусив би пам'ятати id доставок вічно. Час без `SET NX` дозволяє повторити запит багато разів за 5 хвилин. Разом: старе відкидає час, свіже повторення — Redis, а ключі живуть лише 600 с.
    6. Відправник підписує байти, які надсилає. `json.loads` + `json.dumps` дає інші байти (пробіли, порядок ключів), і підписи не збігалися б навіть для справжнього запиту. До того ж розбирати JSON до перевірки — означає обробляти дані невідомо від кого.
    7. Порівняння секрету за сталий час (`compare_digest`): результат той самий, що в `!=`, різниця лише в часі (`294 passed` з `!=`). І bcrypt у пулі потоків: з прямим викликом теж `294 passed`, бо тест не робить одночасних запитів. Обидва — правила в `CLAUDE.md` кроку і пункти рецензії.
    8. Відправник, що не дочекався відповіді, повторює доставку з новим часом — отже з новим підписом. Ключ «підпис» вважав такий повтор новою доставкою, і збір ішов удруге (стара версія кроку: два `202` з різними `job_id`). Id доставки однаковий для всіх повторів однієї події і входить у підпис, тож його не підмінити. `200` з тим самим завданням — це правда («подію прийнято»), і відправник перестає повторювати; `409` виглядав би для нього як помилка.
    9. Ліміт на адресу не бачить атаки з тисячі адрес: кожна має свої 5 спроб. Лічильник на ім'я рахує невдачі з усіх адрес разом і після 20 закриває вхід під цим ім'ям на 15 хв, не запускаючи bcrypt. Ціна — той самий механізм дозволяє атакувальнику на 15 хв закрити вхід і справжньому адміну.
    10. Кожен шар `BaseHTTPMiddleware` змінює, коли закінчуються фонові задачі відносно відповіді. З третім таким шаром тести фонового аналізу іноді падали (`KeyError: 'job_id'`): `pytest -m integration` на кроці 8 — 3 падіння з 20 запусків, з чистим ASGI — 0 з 25. Заголовкам не потрібне тіло: досить дописати їх у `http.response.start`.

## Що далі { #next }

[Крок 9. Telegram-бот](../09_telegram_bot/index.md) — бот на тому самому API. Webhook Telegram приходить на `news_hub` і перевіряється `verify_secret_token`; секрети (`JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `WEBHOOK_SECRET`) і далі — лише в змінних середовища, а в кроках 10–12 — у середовищі контейнера і секретах CI, не в образі й не в git.
