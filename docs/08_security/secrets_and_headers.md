# Секрети, заголовки, проксі й ліміт входу

## Проблема { #problem }

Паролі захешовано, токени підписано, webhook перевіряються — і все це тримається на кількох рядках у змінних середовища. Секрет `change-me` з прикладу підбирається офлайн за кілька спроб. Застосунок за nginx бачить усіх клієнтів з однієї адреси, а якщо довіритись заголовку `X-Forwarded-For` — клієнт сам обирає собі IP і обходить ліміт входу. `request.url_for` будує посилання з `Host`, який надіслав атакувальник. Токен з адреси скидання пароля опиняється в журналі доступу. Це не окремі вразливості коду, а **налаштування навколо** нього — те, що OWASP називає Security Misconfiguration.

## Ментальна модель { #mental-model }

```mermaid
flowchart LR
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef decision fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef error    fill:#ffebee,stroke:#c62828,stroke-width:3px;
    classDef warning  fill:#fff8e1,stroke:#e65100,stroke-width:2px;

    C["клієнт"] --> N["nginx<br>TLS, X-Forwarded-*"]
    N --> P["ProxyHeaders<br>вірити лише nginx"]
    P --> T{"TrustedHost:<br>свій Host?"}
    T -- "ні" --> E400["400"]
    T -- "так" --> L["ліміт входу<br>IP + ім'я"]
    L --> A["маршрут<br>секрети з env"]
    A --> H["відповідь +<br>заголовки безпеки"]
    A -.-> LOG["журнал<br>без секретів"]

    class C,N,A step
    class P,L warning
    class T decision
    class E400 error
    class H,LOG success
```

Порядок важливий: `ProxyHeadersMiddleware` — **зовнішній** (у Starlette — доданий останнім), щоб усі шари всередині вже бачили справжні IP і схему.

## Секрети { #secrets }

### Слабкий секрет ламається офлайн { #weak-secret }

Підпис HS256 перевіряється без сервера: маючи **один** токен (з журналу, з `localStorage`, із власного входу), атакувальник перебирає секрети на своїй машині скільки завгодно. [`examples/security/headers_demo.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/security/headers_demo.py):

```python title="headers_demo.py (фрагмент)"
token = jwt.encode({"sub": "olena", "role": "user"}, weak, algorithm="HS256")          # перехоплений токен
for n, guess in enumerate(wordlist, 1):
    try:
        jwt.decode(token, guess, algorithms=["HS256"])
    except jwt.InvalidSignatureError:
        continue
    forged = jwt.encode({"sub": "olena", "role": "admin"}, guess, algorithm="HS256")
```

```text
--- 1. слабкий секрет JWT ламається офлайн
   PyJWT: InsecureKeyLengthWarning — The HMAC key is 9 bytes long, which is below the minimum rec…
   секрет знайдено за 5 спроб: 'change-me'; підроблено role=admin: admin
   secrets.token_urlsafe(32): 43 символів, 256 біт випадковості
```

- **Секрет — лише з `secrets`**: `secrets.token_urlsafe(32)` дає 32 випадкові байти (256 біт). `random`, UUID, «придумане слово» — ні.
- **Без значення за замовчуванням.** `os.getenv("JWT_SECRET", "change-me")` у публічному коді — це секрет, який знають усі. Немає змінної — застосунок не стартує ([Налаштування](../02_typing_and_pydantic/settings.md#startup)).
- **Окремий секрет на кожне призначення**: підпис JWT, підпис webhook, cookie сесій. Витік одного не відкриває решту, і кожен можна змінити окремо.
- **PyJWT попереджає** про ключ коротший за 32 байти (`InsecureKeyLengthWarning`) — але попередження в журналі ніхто не читає. Довжину перевіряють при старті.

Де зберігати і як не надрукувати — `SecretStr`, `.env` поза git, `secrets_dir`: [Налаштування з середовища](../02_typing_and_pydantic/settings.md#secret). Як секрети доходять до контейнера й CI — [крок 11](../tutorials/11_compose_deploy/env_secrets.md) і [крок 12](../tutorials/12_ci_cd/permissions_and_publish.md#secrets).

### Ротація ключа через `kid` { #key-rotation }

Секрет JWT змінюють планово або після витоку. Якщо просто замінити — усі виходять одночасно. Плавніше: кілька ключів з іменами, ім'я ключа — у заголовку токена (`kid`).

```python title="headers_demo.py (фрагмент)"
keys = {"2026-10": secrets.token_urlsafe(32), "2026-11": secrets.token_urlsafe(32)}
CURRENT = "2026-11"


def verify(token: str) -> dict:
    kid = jwt.get_unverified_header(token).get("kid")       # заголовок ще не перевірено: лише вибір ключа зі СВОГО словника
    if kid not in keys:
        raise jwt.InvalidTokenError(f"невідомий kid {kid!r}")
    return jwt.decode(token, keys[kid], algorithms=["HS256"])
```

```text
--- 2. ротація ключа JWT через kid
   під час ротації: старий → olena | новий → olena
   старий після видалення ключа: InvalidTokenError — невідомий kid '2026-10'
   kid=../../etc/passwd: InvalidTokenError — невідомий kid '../../etc/passwd'
```

- Нові токени підписуються `CURRENT`; старі перевіряються своїм ключем, доки той у словнику. Через строк життя токенів старий ключ видаляють.
- **`kid` — дані від атакувальника** (заголовок ще не перевірено). Лише пошук у своєму словнику: не шлях до файлу, не SQL, не URL для завантаження ключа.
- Після **витоку** плавної ротації немає: старий ключ видаляють одразу, і всі входять знову.

!!! warning "Секрет, що потрапив у git, — скомпрометований"
    Видалити коміт не допоможе: історію вже могли скопіювати (форки, кеш CI, локальні клони). Секрет змінюють, а старий вважають відомим усім. Хто знає секрет підпису, той сам випускає «справжні» токени для будь-кого — з будь-яким `exp` — без жодного пароля.

## Заголовки безпеки { #security-headers }

JSON API не рендерить HTML, але відповідь може відкрити браузер: помилка, файл, `/docs`. Кілька заголовків закривають цілі класи атак. Найпростіше — middleware:

```python title="headers_demo.py (фрагмент)"
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if not request.url.path.startswith("/docs"):         # Swagger UI тягне скрипти з CDN — суворий CSP його зламає
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        response.headers.setdefault("Cache-Control", "no-store")
    if request.url.scheme == "https":                    # HSTS має сенс лише у відповіді по HTTPS
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response
```

```text
--- 3. заголовки безпеки
   /api/me: {'x-content-type-options': 'nosniff', 'referrer-policy': 'no-referrer', 'content-security-policy': "default-src 'none'; frame-ancestors 'none'", 'cache-control': 'no-store'}
   /docs: CSP: None | зовнішні скрипти: ['https://cdn.jsdelivr.net']
   docs_url=None: /docs → 404 | /openapi.json → 404
```

| Заголовок | Від чого | Для JSON API |
|---|---|---|
| `X-Content-Type-Options: nosniff` | браузер «вгадує» тип і виконує JSON/текст як HTML чи скрипт | завжди |
| `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` | відповідь API, відкрита як сторінка, нічого не завантажує й не вбудовується в `<iframe>` | завжди, крім `/docs` |
| `Cache-Control: no-store` | відповіді з персональними даними й токенами в кеші проксі чи браузера | для автентифікованих відповідей |
| `Strict-Transport-Security` | перший запит по `http://` перехоплюють до перенаправлення на HTTPS | лише по HTTPS; спершу малий `max-age` |
| `Referrer-Policy: no-referrer` | адреса з токеном іде в `Referer` на чужі сайти | завжди |
| `X-Frame-Options: DENY` | clickjacking у старих браузерах | `frame-ancestors` у CSP його замінює |

- **`/docs` і CSP.** Swagger UI FastAPI завантажує скрипти й стилі з `cdn.jsdelivr.net`; `default-src 'none'` його зламає. Або виняток для `/docs`, як тут, або власні копії файлів ([FastAPI — Custom Docs UI Static Assets](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/)).
- **`/docs` у продакшні** — повна карта API для будь-кого. Для публічного API це нормально; для внутрішнього — `docs_url=None, openapi_url=None` з налаштувань.
- **HSTS — незворотний на `max-age`.** Браузер пам'ятає «лише HTTPS» стільки, скільки сказано; помилка в сертифікаті — і сайт недоступний. Починають з хвилин.
- **Ставити в одному місці.** Заголовки, які додає nginx (`add_header`), і ті, що додає застосунок, легко подвоїти чи загубити; `setdefault` у middleware не перезаписує наявні.
- **`@app.middleware("http")` — не безкоштовний.** Кожен такий шар — `BaseHTTPMiddleware`, який обгортає відповідь і змінює, коли закінчуються фонові задачі відносно неї. Для заголовків тіло не потрібне, тож у застосунку з `BackgroundTasks` їх краще ставити чистим ASGI-middleware — як у News Hub нижче.

## `Host` і `TrustedHostMiddleware` { #trusted-host }

`request.url_for(...)` і `request.base_url` будують адресу з заголовка `Host` — а його надсилає клієнт:

```text
--- 4. Host-заголовок і TrustedHostMiddleware
   без TrustedHost, Host: evil.example → 200 {'link': 'http://evil.example/reset/t0k3n'}
   з TrustedHost,   Host: evil.example → 400 Invalid host header
   з TrustedHost,   Host: api.example.com → 200 {'link': 'http://api.example.com/reset/t0k3n'}
```

Атакувальник просить скидання пароля жертви з `Host: evil.example` — і жертва отримує лист зі справжнім токеном на сайт атакувальника. Захист — два шари: `TrustedHostMiddleware(allowed_hosts=["api.example.com"])` (те саме робить `ALLOWED_HOSTS` у Django, [Django-книга](https://nikoriakviktor.github.io/notes_chat_app/07_auth_and_security/django_security_architecture_full/)) і адреси в листах — з налаштувань, а не з запиту. `nginx` з `server_name _` пропускає будь-який `Host` далі.

## HTTPS і IP клієнта за проксі { #proxy }

TLS зазвичай знімає nginx (чи балансувальник), і до застосунку приходить звичайний HTTP з адреси проксі. Справжні адресу й схему проксі передає заголовками `X-Forwarded-For` і `X-Forwarded-Proto` — а їх може надіслати й сам клієнт. uvicorn має `ProxyHeadersMiddleware`, який читає ці заголовки **лише від довірених адрес** (`--forwarded-allow-ips`, змінна `FORWARDED_ALLOW_IPS`; за замовчуванням `127.0.0.1`):

```text
--- 5. за проксі: IP клієнта і схема
   ProxyHeaders не підключено             → {'client': '172.28.0.10', 'scheme': 'http'} HSTS: False
   напряму від клієнта, довіряємо nginx   → {'client': '203.0.113.7', 'scheme': 'http'} HSTS: False
   через nginx (172.28.0.10)              → {'client': '1.2.3.4', 'scheme': 'https'} HSTS: True
   trusted_hosts='*', напряму             → {'client': '1.2.3.4', 'scheme': 'https'} HSTS: True
   XFF «підробка, справжній» через nginx  → {'client': '198.51.100.9', 'scheme': 'https'}
```

У кожному рядку клієнт надсилає `X-Forwarded-For: 1.2.3.4` і `X-Forwarded-Proto: https`.

- **Без проксі-заголовків** усі клієнти — `172.28.0.10` (nginx): один лічильник ліміту на всіх.
- **Довіряємо лише nginx**: клієнт, що прийшов напряму, своєю «адресою» нічого не досяг.
- **`trusted_hosts="*"`** — підробка працює: будь-хто обирає собі IP і схему. Так обходять ліміт входу (розбір на справжньому Compose — [крок 11](../tutorials/11_compose_deploy/nginx_real_ip.md#trust-all)).
- **Ланцюжок `1.2.3.4, 198.51.100.9`**: uvicorn іде справа наліво й бере першу адресу, що **не** є довіреним проксі. Тому навіть якщо проксі дописує адресу до клієнтського заголовка, результат правильний — поки довіряють лише своєму проксі.

```text
--- 6. HTTPSRedirectMiddleware за проксі
   без ProxyHeaders, nginx уже зняв TLS → 307 https://api.example.com/api/me (і так щоразу)
   з ProxyHeaders                        → 200 {'client': '172.28.0.10', 'scheme': 'https'}
```

`HTTPSRedirectMiddleware` без проксі-заголовків бачить `http` у кожному запиті — навіть у тому, що прийшов по HTTPS до nginx, — і перенаправляє назавжди. Те саме з HSTS, `url_for` і `Secure`-cookie: усе, що залежить від схеми, за проксі працює правильно лише з довіреними `X-Forwarded-Proto`.

## Журнали без секретів { #logging }

Журнали живуть довше за токени, їх читає більше людей, і вони копіюються в системи збору. Що туди потрапляє без жодного злого наміру:

```text
--- 7. журнали без секретів
   INFO "GET /reset?token=t0k3n-from-email HTTP/1.1" 200
   INFO headers={'authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJvbGVuYSJ9.XiY0NoflXMXLS-7LmC3yY1ztSuP-PbWgUw2PbJGl9Tc', 'user-agent': 'curl/8'}
   INFO "GET /reset?token=*** HTTP/1.1" 200
   INFO headers={'authorization': 'Bearer ***', 'user-agent': 'curl/8'}
```

```python title="headers_demo.py (фрагмент)"
class RedactSecrets(logging.Filter):
    PATTERNS = [(re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1***"),
                (re.compile(r"((?:token|password|secret|api_key)=)[^&\s]+", re.I), r"\1***")]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern, replacement in self.PATTERNS:
            message = pattern.sub(replacement, message)
        record.msg, record.args = message, None
        return True
```

- **Секрети не в URL.** Журнал доступу uvicorn і nginx пише шлях **разом з query**. Токен у посиланні з листа — неминучий, тому він одноразовий і короткий; токени API — лише в заголовках.
- **Не журналювати заголовки й тіла цілком.** `Authorization`, `Cookie`, `X-Api-Key`, поля `password` — або взагалі не писати, або маскувати. Фільтр — страховка, а не основний захист: регулярні вирази пропустять формат, якого не передбачили.
- **Помилки валідації.** `422` і `ValidationError` містять `input` — значення, що не пройшло перевірку; для поля пароля це пароль ([Налаштування](../02_typing_and_pydantic/settings.md#startup)).
- **Але журналювати події безпеки**: невдалі входи, `403`, відхилені підписи, спрацювання ліміту — з IP та ім'ям, без пароля. Це те, що OWASP Top 10:2025 називає A09 Security Logging and Alerting Failures.

## Ліміт спроб входу { #login-rate-limit }

Повільний хеш робить кожну спробу дорогою, ліміт — обмежує їхню кількість. Питання — **за яким ключем** рахувати:

```text
--- 8. ліміт входу: ключ — IP, ім'я чи обидва
   20 спроб з 20 IP на olena     → заблоковано {'ip': 0, 'user': 15}
   20 спроб з одного IP на 20 імен → заблоковано {'ip': 15, 'user': 0}
```

| Атака | Ліміт за IP | Ліміт за ім'ям |
|---|---|---|
| перебір пароля одного акаунта з ботнету (credential stuffing, brute force) | не бачить: кожен IP робить одну спробу | ловить |
| один поширений пароль до тисяч акаунтів з одного IP (password spraying) | ловить | не бачить: кожне ім'я — одна спроба |
| те саме з ботнету | ні | ні — потрібні сигнали ширше: частка невдалих входів, CAPTCHA, другий фактор |

Тому лічильників два: за IP і за ім'ям (краще — за парою й окремо за ім'ям з вищою межею). Ліміт за ім'ям має ціну: атакувальник може **навмисно** блокувати чужий акаунт. Замість повного блокування — зростаюча затримка, CAPTCHA після N спроб, сповіщення власнику; вхід з уже відомого пристрою чи IP можна не рахувати. Відповідь — `429` з `Retry-After`. Як влаштований сам лічильник (Redis `INCR` + `EXPIRE NX`, фіксоване вікно) — [Rate limit у кроці 4](../tutorials/04_middleware_redis/rate_limit.md).

## У News Hub { #news-hub }

| Тема | News Hub (крок 12) |
|---|---|
| секрети | `JWT_SECRET`, `WEBHOOK_SECRET` ≥ 32 символи, `ADMIN_PASSWORD_HASH` — повний bcrypt-хеш; інакше застосунок не стартує; `python -m news_hub.security` друкує `secrets.token_urlsafe(48)` |
| де секрети | `.env` поза git, у репозиторії — `.env.example`; Compose `env_file: .env`; CI — секрети GitHub ([крок 11](../tutorials/11_compose_deploy/env_secrets.md), [крок 12](../tutorials/12_ci_cd/permissions_and_publish.md#secrets)) |
| секрети в історії git | job `supply-chain` у CI: gitleaks 8.30.1 по всій історії, з `.gitleaks.toml` (allowlist чотирьох навчальних значень) |
| окремі секрети | JWT, webhook, Telegram (`TELEGRAM_WEBHOOK_SECRET`, 32–256 символів) — три різні змінні |
| ротація | `kid` немає: зміна `JWT_SECRET` — вихід для всіх |
| заголовки безпеки | `SecurityHeadersMiddleware` (`middleware.py`, чистий ASGI) на кожній відповіді, зокрема `429` і `404`: `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy: same-origin`; CSP `default-src 'none'; frame-ancestors 'none'` — усюди, крім `/docs` і `/redoc` |
| `/docs` | `DOCS_ENABLED` (за замовчуванням `true`; `0`/`false`/`no`/`off` — вимкнено): без нього `/docs`, `/redoc` і `/openapi.json` — `404`; Compose ставить `DOCS_ENABLED: ${DOCS_ENABLED:-false}` |
| nginx | `server_tokens off` — `Server: nginx` без версії; власних заголовків не додає; HSTS — лише в майбутньому блоці `listen 443 ssl` |
| `TrustedHost` | немає, nginx — `server_name _`; застосунок не будує адрес з `Host` (`url_for` не використовується), тож зараз це без наслідків |
| HTTPS | TLS знімається перед nginx (certbot чи Caddy, [крок 11](../tutorials/11_compose_deploy/deploy.md#https)); `nginx.conf` передає `X-Forwarded-Proto` |
| IP клієнта | nginx **перезаписує** `X-Forwarded-For` адресою з'єднання; `FORWARDED_ALLOW_IPS: ${NGINX_IP:-172.28.0.10}` — uvicorn вірить лише nginx з фіксованою адресою ([крок 11](../tutorials/11_compose_deploy/nginx_real_ip.md#change)) |
| журнали | `request_context` пише `request.url.path` без query; токени — лише в заголовках; помилки старту — без значень секретів |
| ліміт входу | два лічильники: за IP — 5 спроб за 300 с (`rate:login:<ip>`, рахує всі); за ім'ям — `LoginGuard`, 20 **невдалих** за 900 с з усіх адрес разом (`LOGIN_FAIL_LIMIT`, `LOGIN_FAIL_WINDOW`) |
| відповідь з токеном | `Cache-Control: no-store`; bcrypt — у `run_in_threadpool` |

### Було → стало { #news-hub-fixes }

**Ліміт входу.** *Було:* лічильник лише за IP. Перебір пароля єдиного адміна з багатьох адрес обмежувала тільки вартість bcrypt — рядок «20 спроб з 20 IP на olena → заблоковано `{'ip': 0, …}`» з [демо вище](#login-rate-limit). *Стало:* `LoginGuard` у `security.py` рахує невдалі входи на ім'я — ключ `login:fail:<sha256(casefold(ім'я))[:32]>`, `INCR` + `EXPIRE NX` в одній транзакції. Ім'я в ключі — хешем: у Redis не потрапляє довільний рядок від клієнта. Після межі `POST /api/admin/token` одразу відповідає `429` з `Retry-After` і «забагато невдалих входів під цим іменем; спробуй через N с», навіть не запускаючи bcrypt; вдалий вхід скидає лічильник. Сам лічильник на новому коді (fakeredis):

```text
межа: 20 невдач за 900 с; ключ: login:fail:8c6976e5b5410415bde908bd4dee15df
після 19 невдач: retry_after = 0
після 20-ї (як 'Admin'): retry_after = 900
інше ім'я 'editor': retry_after = 0
після вдалого входу: retry_after = 0
```

Останній рядок — виклик `succeeded` напряму: через API під час блокування до перевірки пароля не дійти. Ціна — та, що в [таблиці вище](#login-rate-limit): атакувальник може на 15 хвилин закрити вхід і справжньому адміну. Для єдиного адміна це обрано свідомо: краще, ніж необмежений підбір. Доводять тести `test_login_guard_counts_per_name_and_resets_on_success` (`tests/unit/test_security.py`) і `test_login_lockout_counts_failures_per_name_from_any_address` (`tests/integration/test_admin_api.py`). Другий тест знімає ліміт за IP (так імітується тисяча адрес): 20 разів `401`, потім `429` навіть на правильний пароль, а інше ім'я — далі `401`.

**Заголовки й `/docs`.** *Було:* жодного заголовка безпеки ні в застосунку, ні в `nginx.conf`; `/docs` і `/openapi.json` — відкрита карта API на публічному сервері; `Server: nginx/<версія>`. *Стало:* `SecurityHeadersMiddleware`, `DOCS_ENABLED=false` у Compose, `server_tokens off`. Цікава деталь — чому middleware саме чистий ASGI, а не ще один `@app.middleware("http")`. Із третім шаром `BaseHTTPMiddleware` тести фонового аналізу почали іноді падати (`KeyError: 'job_id'`): цей шар змінив, коли фонові задачі закінчуються відносно відповіді. Заміряно на `pytest -m integration` кроку 8: старий код — 0 падінь з 8 запусків, з додатковим `BaseHTTPMiddleware` — 3 з 20, із чистим ASGI — 0 з 25. Це гонка: на іншій машині чи в іншому кроці вона може й не проявитись, тому виправлення — у шарі, а не в тестах. Шар стоїть між `request_context` і `rate_limit`, тому `429` теж отримує заголовки. Доводять `test_security_headers_on_every_answer` (заголовки на `200`, `404` і `401`; на `/docs` — без CSP, але з `X-Frame-Options`), `test_docs_enabled` (7 значень змінної) і перевірки в `smoke.sh` кроку 12: через nginx `/docs` → `404`, `X-Content-Type-Options: nosniff`, `Server: nginx` без версії.

**Відповідь з токеном.** *Було:* без `Cache-Control`, а bcrypt у `async def` займав event loop на час перевірки ([Паролі](passwords.md#news-hub)). *Стало:* `Cache-Control: no-store` (перевіряє `tests/integration/test_admin_api.py`) і `await run_in_threadpool(authenticate, …)`.

## Типові помилки { #mistakes }

| Помилка | Наслідок | Як правильно |
|---|---|---|
| секрет за замовчуванням у коді | секрет знають усі, хто бачив код | без значення за замовчуванням, перевірка при старті |
| короткий чи «придуманий» секрет HS256 | офлайн-перебір за один перехоплений токен | `secrets.token_urlsafe(32)` і довше |
| один секрет на все | витік одного — усе відкрито | окремий на кожне призначення |
| `kid` як шлях до файлу чи ключ у SQL | ін'єкція через заголовок токена | лише пошук у своєму словнику |
| `FORWARDED_ALLOW_IPS=*` / `trusted_hosts="*"` | клієнт обирає собі IP і схему | адреса свого проксі |
| `HTTPSRedirectMiddleware` за проксі без проксі-заголовків | нескінченне перенаправлення | `ProxyHeadersMiddleware` з довіреним проксі, або перенаправлення в nginx |
| посилання з `request.url_for` без `TrustedHost` | лист з доменом атакувальника | `TrustedHostMiddleware` і адреса з налаштувань |
| суворий CSP і на `/docs` | Swagger UI не завантажується | виняток для `/docs` або свої статичні файли |
| HSTS з великим `max-age` одразу | помилка в TLS — сайт недоступний місяцями | починати з хвилин |
| токени в query | токен у журналах доступу й `Referer` | заголовки; одноразові короткі токени в посиланнях |
| журналювати `request.headers` цілком | `Authorization` і cookie в журналах | білий список полів журналу |
| ліміт входу лише за IP | перебір з багатьох адрес | IP і ім'я |
| ліміт за ім'ям з повним блокуванням | будь-хто блокує чужий акаунт | затримка, CAPTCHA, сповіщення |
| ще один `@app.middleware("http")` лише заради заголовків | інший порядок завершення фонових задач, нестабільні тести | чистий ASGI-middleware |

## Налагодження { #debugging }

- **Які заголовки реально йдуть клієнту?** `curl -sI https://api.example.com/api/news` — через nginx, а не напряму до uvicorn: проксі може додати чи прибрати заголовки.
- **Яку адресу бачить застосунок?** Тимчасовий ендпоінт або рядок журналу з `request.client.host` і `request.url.scheme`; порівняти з `$remote_addr` у журналі nginx.
- **Перевірка конфігурації перед деплоєм.** У Django для цього є `manage.py check --deploy` (`DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`, HSTS, `Secure`-cookie). У FastAPI вбудованого немає — той самий список перевірок робить код старту (fail fast) і тести: «застосунок без `JWT_SECRET` не стартує», «`/docs` вимкнено в продакшні».
- **Чи немає секретів у git?** `git log -p | grep -E 'SECRET|PASSWORD|TOKEN'` — грубо; точніше — сканери на кшталт `gitleaks` у CI і GitHub secret scanning. Навчальні значення (токени в тестах і прикладах) сканер теж знаходить — їх додають в allowlist поіменно, а не вимикають правило.

## Безпека й межі { #security }

- **Заголовки — лише для браузера.** Скрипт чи бот їх ігнорує; від атак на API вони не захищають, лише від атак через браузер користувача.
- **TLS — до самого застосунку чи лише до проксі?** Між nginx і API в одній приватній мережі Compose — звичайний HTTP. Якщо мережа спільна з іншими (хмара, кілька серверів), — TLS і там.
- **Секрет у пам'яті процесу** читає будь-хто з доступом до процесу чи змінних середовища контейнера (`docker inspect`). Сховища секретів (Vault, хмарні KMS, Docker secrets) скорочують коло тих, хто його бачить, але не прибирають секрет з пам'яті.
- **Ліміт — не автентифікація.** Він сповільнює перебір, але не зупиняє розподілену атаку; для людей — другий фактор.

## Питання { #questions }

1. Чому для HS256 важлива довжина й випадковість секрету, а не лише «щоб ніхто не знав»?
2. Як змінити секрет JWT без того, щоб усі вийшли одночасно?
3. Чому значенню `kid` не можна довіряти?
4. Чому `FORWARDED_ALLOW_IPS=*` небезпечний? Що бачить застосунок без жодних проксі-заголовків?
5. Чому `HTTPSRedirectMiddleware` за nginx може перенаправляти нескінченно?
6. Як заголовок `Host` може зробити скидання пароля небезпечним?
7. Чому суворий CSP ламає `/docs`?
8. Чому ліміт входу лише за IP недостатній, а лише за ім'ям — небезпечний?

??? success "Відповіді"

    1. Підпис перевіряється офлайн: маючи один токен, секрет перебирають на своїй машині без обмежень. Короткий чи словниковий секрет знаходиться за секунди.
    2. Кілька ключів з іменами (`kid` у заголовку токена): нові підписуються новим, старі перевіряються старим, доки не мине їхній строк; потім старий видаляють.
    3. Заголовок токена читається до перевірки підпису — це дані від атакувальника. Лише пошук у своєму словнику ключів.
    4. uvicorn довіряє `X-Forwarded-For` від будь-кого — клієнт обирає собі IP і обходить ліміти. Без проксі-заголовків застосунок бачить адресу проксі для всіх клієнтів.
    5. TLS знято на nginx, до застосунку приходить `http`; без довірених `X-Forwarded-Proto` middleware бачить `http` у кожному запиті й щоразу перенаправляє на `https`.
    6. `url_for` будує посилання з `Host` запиту: атакувальник просить скидання з `Host: evil.example`, і жертва отримує справжній токен на чужий домен.
    7. Swagger UI завантажує скрипти й стилі з `cdn.jsdelivr.net`, а `default-src 'none'` забороняє будь-які зовнішні ресурси.
    8. Лише за IP не бачить перебору одного акаунта з багатьох адрес; лише за ім'ям дає будь-кому заблокувати чужий акаунт і не бачить «один пароль — багато імен».

## Що далі { #next }

[OWASP API Security Top 10 на FastAPI і News Hub](owasp_api_top10.md) — усі розділи частини, зібрані в одну карту ризиків: що закрито, що ні.

**Джерела:** Python — [`secrets`](https://docs.python.org/3/library/secrets.html), [`logging` — Filter](https://docs.python.org/3/library/logging.html#filter-objects); [PyJWT — Usage](https://pyjwt.readthedocs.io/en/stable/usage.html); Starlette — [Middleware: TrustedHostMiddleware, HTTPSRedirectMiddleware](https://starlette.dev/middleware/); uvicorn — [Settings: proxy headers](https://uvicorn.dev/settings/#http), [Deployment: running behind a proxy](https://uvicorn.dev/deployment/#running-behind-nginx); FastAPI — [Behind a Proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/), [Custom Docs UI Static Assets](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/); OWASP — [HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html), [Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html), [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html), [Authentication Cheat Sheet — login throttling](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), [Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html); [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security); Django — [Deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
