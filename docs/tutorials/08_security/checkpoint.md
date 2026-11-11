# Контрольна точка: крок 8

## Перевір, що крок робочий { #check }

З папки `steps/08_security`:

```text
$ pytest -q -p no:cacheprovider
........................................................................ [ 25%]
........................................................................ [ 51%]
........................................................................ [ 77%]
...............................................................          [100%]
279 passed, 2 deselected in 18.66s
$ mypy --strict news_hub
Success: no issues found in 18 source files
```

Порівняно з кроком 7 (168 тестів) додалось 111 тестів безпеки: 62 unit (пароль і токени, адреси, підписи) і 49 integration (хто може писати, SSRF на локальних серверах, webhook через API). Перелік — у [Тестах безпеки](security_tests.md#files).

## Чекліст { #checklist }

- [ ] `python -m news_hub.security` друкує `ADMIN_PASSWORD_HASH='$2b$12$…'` і `JWT_SECRET='…'`; обидва — в середовищі, в одинарних лапках.
- [ ] Без цих змінних `DELETE /api/news` → `503`, а `GET /api/news` → `200`.
- [ ] З `JWT_SECRET=change-me-in-production` uvicorn не стартує: `RuntimeError: JWT_SECRET має бути не коротшим за 32 символи`.
- [ ] `DELETE /api/news` без токена → `401` і заголовок `WWW-Authenticate: Bearer`; з токеном адміна → `200`.
- [ ] Шоста спроба входу за 5 хвилин → `429` з `Retry-After`.
- [ ] У `/docs` є кнопка **Authorize**, 14 операцій з замком.
- [ ] `POST /api/sources` з `http://169.254.169.254/latest/meta-data/` → `400`; з `http://localhost/admin` → `201`, але `/fetch` → `400 … loopback`.
- [ ] Підписаний webhook → `202`, той самий удруге → `409`, змінене тіло → `401`.
- [ ] Можеш пояснити, чому заміна `hmac.compare_digest` на `!=` не валить жодного тесту.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `RuntimeError: ADMIN_PASSWORD_HASH — bcrypt-хеш ($2b$…), а не пароль` при старті | у змінній пароль, а не хеш; або хеш у **подвійних** лапках: shell підставив `$2`, `$12`, і з `"$2b$12$…"` лишилось `b2…` | `python -m news_hub.security`, хеш — в одинарних лапках: `export ADMIN_PASSWORD_HASH='$2b$12$…'` |
| `RuntimeError: JWT_SECRET має бути не коротшим за 32 символи` | короткий секрет або задано лише хеш без секрету | секрет з `python -m news_hub.security` (64 символи) |
| `503 адмін-доступ не налаштовано` | змінні задані в іншому терміналі чи після запуску uvicorn | `export …` у тому самому shell, потім перезапуск |
| `429 забагато запитів: 5 за 300 с` на правильний пароль | ліміт рахує **всі** спроби входу, і вдалі теж | зачекай `Retry-After` секунд; для розробки — `LOGIN_RATE_LIMIT` більше |
| `401 токен прострочений` у Postman чи Swagger | токен живе `JWT_EXPIRE_MINUTES` (30) хвилин | новий вхід: запит «Вхід адміна → token» або Authorize ще раз |
| локальна RSS-стрічка `http://localhost:8080/rss` → `400 … порт 8080` чи `… loopback` | `safe_fetch` за замовчуванням ходить лише в публічний інтернет на 80/443 | у тестах — явна `FetchPolicy` через `dependency_overrides[get_fetch_policy]`, а не послаблення `DEFAULT_POLICY` |
| webhook → `401 підпис не збігається`, хоча секрет правильний | відправник підписав одні байти, а надіслав інші (`json.dumps` з іншими пробілами, `curl -d @file` з переносом рядка) | підписуй рівно ті байти, які надсилаєш |
| webhook → `401 запит старший за 300 с` | годинник відправника відстає чи спішить більше ніж на 5 хв, або запит підписали заздалегідь | синхронізуй час (NTP); підписуй перед самим надсиланням |
| повтор webhook після збою мережі → `409` | той самий підпис удруге за 10 хв | при повторі — новий час і новий підпис |

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
29 passed in 1.60s
$ pytest -q tests/integration/test_api.py
1 failed, 16 passed in 1.48s
$ mypy --strict news_hub
Success: no issues found in 18 source files
```

- **Тест захисту нічого не дописує.** `test_every_other_endpoint_requires_admin` знаходить `require_admin` у залежностях нового маршруту, а `test_anonymous_gets_401` сам додає для нього випадок: було 27 тестів у файлі — стало 29 (`test_admin_me` + `[GET-/api/admin/me]`). Якби `AdminDep` забули, перший тест показав би `('GET', '/api/admin/me')` у різниці множин.
- **Червоний `test_openapi_lists_endpoints`** — так і має бути: він перелічує всі шляхи API, і новий шлях `/api/admin/me` треба дописати в його множину. Це другий запобіжник: новий ендпоінт не з'явиться в API непомітно.

### Зміни приклад { #modify }

1. У фікстурі `local_policy` (`tests/integration/test_sources_ssrf.py`) додай `max_redirects=0` і запусти `pytest tests/integration/test_sources_ssrf.py`. Який тест впав і з яким повідомленням? Чому тести перенаправлень на внутрішній сервіс досі зелені?
2. У `verify_signature` заміни `hmac.compare_digest(...)` на `signature != sign(...)`. Скільки тестів впало?

??? success "Що покаже запуск"

    1. Червоний один — `test_fetch_rss_source`:

        ```text
        E       AssertionError: {'detail': 'джерело недоступне: більше 0 перенаправлень'}
        FAILED tests/integration/test_sources_ssrf.py::test_fetch_rss_source - Assert...
        1 failed, 13 passed in 0.76s
        ```

        Стрічка доступна лише через `/moved → /rss`. Решта 13 зелені. Перенаправлення на внутрішній сервіс, метадані й `file://` зупиняє `check_url` **ще до** того, як цикл дійде до ліміту: адресу з `Location` перевіряють першою.

    2. Жодного: `279 passed, 2 deselected`. Результат порівняння той самий, різниться лише **час**: `!=` зупиняється на першому неспівпадінні. Функціональний тест такого не бачить. Тому правило записане в `CLAUDE.md` кроку і перевіряється на рецензії, а не тестом.

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
| Пароль | bcrypt-хеш у середовищі; > 72 байт — «не той пароль»; одна відповідь на чуже ім'я і чужий пароль; 5 спроб за 300 с |
| Налаштування | без значень за замовчуванням: не задано → `503`, задано погано → не стартує |
| Хто може писати | `dependencies=[AdminDep]` + тест, що обходить усі маршрути і порівнює з `PUBLIC` |
| SSRF | перевіряти IP **з'єднання** (resolver), а не рядок URL; кожне перенаправлення; порти, розмір, тип; відповідь не віддавати |
| Webhook | HMAC-SHA256(час + "." + сирі байти тіла), вікно 300 с, `SET NX` проти повтору, `compare_digest`, секрет не в URL |
| Що ловлять тести | атаки — так (підроблені токени, адреси, повтори); витік часу — ні: це рецензія |

## Самоперевірка { #self-check }

1. Чим `401` відрізняється від `403` у `require_admin`? Наведи запит для кожного.
2. Навіщо перевіряти пароль, коли ім'я вже неправильне?
3. Чому `JWT_ALGORITHM` — константа в коді, а не змінна середовища?
4. Чому `http://localhost/admin` пройшов `POST /api/sources`, але не пройшов `/fetch`? Чи не краще перевіряти DNS при додаванні?
5. Навіщо в підписі webhook час, якщо є `SET NX`? І навпаки?
6. Чому підпис рахують від сирих байтів, а не від `json.loads(body)`?
7. Який захист кроку жоден тест не перевіряє і чому?

??? success "Відповіді"

    1. `401` — ми не знаємо, хто це: токена немає, підпис не збігається, строк минув (`DELETE /api/news` без заголовка). `403` — знаємо, хто, але прав немає: справжній токен з `role: user`.
    2. Інакше чуже ім'я відповідає миттєво, а своє — після bcrypt (~0,23 с). Різниця в часі підказує, що ім'я вгадано, і далі треба перебирати лише паролі.
    3. Алгоритм визначає, **як** перевіряти підпис. Якщо його можна змінити ззовні (чи взяти з заголовка токена), атакувальник обере зручний: `none` без підпису або інший, де секрет використовується не так. `algorithms=["HS256"]` у `decode` приймає лише один.
    4. Ім'я без DNS не перевірити, а DNS можна змінити будь-коли після додавання. Перевірка при додаванні дала б хибну впевненість, тому IP перевіряє resolver при **кожному** з'єднанні.
    5. `SET NX` без часу мусив би пам'ятати підписи вічно. Час без `SET NX` дозволяє повторити запит багато разів за 5 хвилин. Разом: старе відкидає час, свіже повторення — Redis, а ключі живуть лише 600 с.
    6. Відправник підписує байти, які надсилає. `json.loads` + `json.dumps` дає інші байти (пробіли, порядок ключів), і підписи не збігалися б навіть для справжнього запиту. До того ж розбирати JSON до перевірки — означає обробляти дані невідомо від кого.
    7. Порівняння секрету за сталий час (`compare_digest`): результат той самий, що в `!=`, різниця лише в часі (`279 passed` з `!=`). Це правило в `CLAUDE.md` кроку і пункт рецензії.

## Що далі { #next }

[Крок 9. Telegram-бот](../09_telegram_bot/index.md) — бот на тому самому API. Webhook Telegram приходить на `news_hub` і перевіряється `verify_secret_token`; секрети (`JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `WEBHOOK_SECRET`) і далі — лише в змінних середовища, а в кроках 10–12 — у середовищі контейнера і секретах CI, не в образі й не в git.
