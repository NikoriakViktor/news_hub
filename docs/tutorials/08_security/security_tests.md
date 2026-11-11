# Тести безпеки

> Крок 8 · розділ 4 з 4. Код: [`tests/unit/`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/08_security/tests/unit), [`tests/integration/`](https://github.com/NikoriakViktor/news_hub/tree/main/steps/08_security/tests/integration), [`tests/integration/conftest.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/tests/integration/conftest.py).
> Теорія: [Частина VIII. Безпека API](../../08_security/README.md).

## Задача { #task }

Захист, який не перевірено атакою, — лише надія. Тести кроку мають довести три речі:

1. кожна перевірка (токен, адреса, підпис) відкидає підробку — кожен відомий спосіб обходу як окремий тест;
2. кожен ендпоінт справді викликає перевірку — і **новий** ендпоінт не забуде її;
3. старі тести кроків 2–7 перевіряють те саме, що й раніше, хоча запис тепер закритий.

І чесно визначити, чого тести **не** бачать.

## Файли й кількість тестів { #files }

| Файл | Що перевіряє | Тестів |
|---|---|---:|
| [`tests/unit/test_security.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/tests/unit/test_security.py) | хеш і сіль, 72 байти, вхід (4 випадки), строк дії; 7 підроблених токенів (інший секрет, `alg: none`, HS512 тим самим секретом, змінений payload, без `role`, без `exp`, не JWT); налаштування з середовища | 16 |
| [`tests/unit/test_safe_fetch.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/tests/unit/test_safe_fetch.py) | 16 адрес `is_public_ip`; 14 заборонених URL; 3 дозволені; явна політика; IPv4 всередині IPv6 | 35 |
| [`tests/unit/test_webhooks.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/tests/unit/test_webhooks.py) | підпис; 8 способів підробити (змінене тіло, інший порядок байтів, чужий секрет, старий і майбутній час, змінений час, немає заголовків, час не число); повтор; секрет Telegram | 11 |
| [`tests/integration/test_admin_api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/tests/integration/test_admin_api.py) | `PUBLIC` = усі незахищені маршрути; кожен закритий без токена → 401 (14 випадків); вхід, 4 погані входи, brute-force → 429, прострочений, `alg: none`, роль → 403, не налаштовано → 503, Swagger | 27 |
| [`tests/integration/test_sources_ssrf.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/tests/integration/test_sources_ssrf.py) | справжній aiohttp проти двох локальних серверів: стрічка через перенаправлення; перенаправлення на внутрішній сервіс, метадані, `file://` → 400 (внутрішній сервер — 0 запитів); HTML, ~2,6 МБ без `Content-Length`, петля → 502; `localhost` за DNS → 400; 5 небезпечних джерел не зберігаються; CRUD джерел | 14 |
| [`tests/integration/test_webhooks_api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/tests/integration/test_webhooks_api.py) | 202 без JWT; 4 × 401; повтор 409; непідписане сміття — 401, а не 422; без секрету — 503 | 8 |
| **разом** | | **111** |

```text
$ pytest -q tests/unit/test_security.py tests/unit/test_safe_fetch.py tests/unit/test_webhooks.py \
      tests/integration/test_admin_api.py tests/integration/test_sources_ssrf.py tests/integration/test_webhooks_api.py
111 passed in 3.88s
```

Ні мережі, ні справжнього DNS-сервера: SSRF-тести працюють проти локальних aiohttp-серверів, а `localhost` резолвиться без мережі.

## Фікстури: `client` — адмін, `anon` — будь-хто { #fixtures }

Секрети для тестів — явні тестові значення в `conftest.py`, задані **до** імпорту застосунку, а не з `.env`:

```python title="tests/integration/conftest.py (фрагмент)"
ADMIN_PASSWORD = "test-admin-password"
os.environ.update({
    "JWT_SECRET": "test-jwt-secret-" + "x" * 32,
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD_HASH": hash_password(ADMIN_PASSWORD, rounds=4),    # 4 раунди — швидко; у проді 12
    "WEBHOOK_SECRET": "test-webhook-secret-" + "y" * 32,
})


@pytest.fixture
def anon() -> Iterator[TestClient]:
    """Крок 8: клієнт без токена — як будь-хто в інтернеті."""
    ...


@pytest.fixture
def client(anon: TestClient) -> TestClient:
    """Синхронний клієнт адміна: застосунок крутиться у своєму потоці й циклі подій (portal)."""
    anon.headers.update(admin_headers())
    return anon
```

Фікстура `client` тепер надсилає токен адміна, тож тести кроків 2–7 перевіряють те саме, що й раніше. Змінились лише два: `test_openapi_lists_endpoints` — нові шляхи в переліку; `test_failed_commit_is_500_not_200` — його власний `TestClient` тепер з токеном (`headers=client.headers`).

## Тест «нічого не забули» { #public }

Небезпека `dependencies=[AdminDep]` — **забути** його на новому ендпоінті. Тому тест не перебирає ендпоінти вручну. Він обходить усі маршрути застосунку і шукає `require_admin` у дереві залежностей кожного:

```python title="tests/integration/test_admin_api.py"
# Єдині ендпоінти без токена адміна. Новий ендпоінт сюди не потрапить сам: або AdminDep, або рішення тут.
PUBLIC = {
    ("GET", "/health"), ("GET", "/api/news"), ("GET", "/api/news/search"), ("GET", "/api/news/count"),
    ("GET", "/api/news/stats"), ("GET", "/api/news/{news_id}"),
    ("POST", "/api/admin/token"),                   # вхід — пароль
    ("POST", "/api/webhooks/scrape"),               # свій захист — підпис HMAC (test_webhooks_api.py)
}


def admin_protected(route: APIRoute) -> bool:
    stack = list(route.dependant.dependencies)
    while stack:
        dependency = stack.pop()
        if dependency.call is require_admin:
            return True
        stack.extend(dependency.dependencies)
    return False


def test_every_other_endpoint_requires_admin() -> None:
    unprotected = {(method, path) for method, path, route in endpoints() if not admin_protected(route)}
    assert unprotected == PUBLIC


@pytest.mark.parametrize(("method", "path"), sorted({(m, p) for m, p, _ in endpoints()} - PUBLIC))
def test_anonymous_gets_401(anon: TestClient, method: str, path: str) -> None:
    url = path.replace("{news_id}", "1").replace("{job_id}", "abc").replace("{source_id}", "1")
    response = anon.request(method, url, json={})
    assert response.status_code == 401, response.text
    assert response.headers["WWW-Authenticate"] == "Bearer"
```

Перший тест перевіряє **структуру** (залежність є), другий — **поведінку** (без токена справді `401`). Параметри другого будуються з маршрутів застосунку, тож новий закритий ендпоінт сам отримує свій випадок.

Перевіримо, що тест ловить забутий захист: у копії кроку прибираємо `dependencies=[AdminDep]` з `DELETE /api/news` і запускаємо файл:

```text
FAILED tests/integration/test_admin_api.py::test_every_other_endpoint_requires_admin
FAILED tests/integration/test_admin_api.py::test_anonymous_gets_401[DELETE-/api/news]
FAILED tests/integration/test_admin_api.py::test_anonymous_cannot_wipe_the_database
FAILED tests/integration/test_admin_api.py::test_expired_token_is_401 - KeyEr...
FAILED tests/integration/test_admin_api.py::test_unsigned_token_is_401 - KeyE...
FAILED tests/integration/test_admin_api.py::test_valid_token_without_admin_role_is_403
FAILED tests/integration/test_admin_api.py::test_not_configured_is_503 - Asse...
FAILED tests/integration/test_admin_api.py::test_swagger_has_authorize_button
8 failed, 19 passed in 2.37s
```

У повідомленні першого тесту видно, який саме маршрут лишився відкритим:

```text
E         Extra items in the left set:
E         ('DELETE', '/api/news')
```

Якщо маршрут **має** бути публічним, його додають у `PUBLIC` — це рішення видно в рецензії коду, а не відкритий ендпоінт, про який ніхто не знає.

## Атаки як тести { #attacks }

Кожен відомий спосіб обійти перевірку — окремий випадок `parametrize`. Підроблені токени:

```python title="tests/unit/test_security.py (фрагмент)"
def forged_tokens() -> dict[str, str]:
    exp = int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())
    claims = {"sub": "admin", "role": "admin", "exp": exp}
    good = create_access_token(SETTINGS, "admin")
    header, _, signature = good.split(".")
    return {
        "інший секрет": jwt.encode(claims, "x" * 64, algorithm="HS256"),
        "alg none": f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}.",
        "HS512 тим самим секретом": jwt.encode(claims, SECRET, algorithm="HS512"),
        "змінений payload": f"{header}.{_b64({**claims, 'sub': 'hacker'})}.{signature}",
        "без role": jwt.encode({"sub": "admin", "exp": exp}, SECRET, algorithm="HS256"),
        "без exp": jwt.encode({"sub": "admin", "role": "admin"}, SECRET, algorithm="HS256"),
        "не JWT": "abc.def",
    }


@pytest.mark.parametrize("case", list(forged_tokens()))
def test_forged_tokens_are_rejected(case: str) -> None:
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(SETTINGS, forged_tokens()[case])
```

«HS512 тим самим секретом» — підпис справжній, але алгоритм інший. Він не пройде, бо `algorithms=[JWT_ALGORITHM]`: сервер не дає токену самому обирати, як його перевіряти.

Для SSRF головна перевірка — не код відповіді, а **лічильник запитів** «внутрішнього» сервера: `assert internal.app[HITS] == []`. Відповідь `400` ще не доводить, що запит не пішов; порожній лічильник — доводить.

```python title="tests/integration/test_sources_ssrf.py (фрагмент)"
@pytest.mark.asyncio
@pytest.mark.parametrize(("path", "reason"), [
    ("/to-internal", "порт"),                 # дозволений сайт перенаправляє на внутрішній сервіс
    ("/to-metadata", "169.254.169.254"),
    ("/to-file", "схема file"),
])
async def test_redirect_is_checked_again(aclient: httpx.AsyncClient, feed: TestServer, internal: TestServer,
                                         local_policy: FetchPolicy, path: str, reason: str) -> None:
    response = await add_and_fetch(aclient, str(feed.make_url(path)))
    assert response.status_code == 400 and reason in response.json()["detail"], response.text
    assert internal.app[HITS] == []
```

Для webhook — випадки підробки й повтору, і окремий тест порядку перевірок: непідписане сміття — `401`, а підписане — `422`.

## Що ловлять тести, а що — ні { #mutations }

Навмисні поломки захисту в копії кроку (код самого кроку не змінюється):

| Поломка | Результат `pytest` |
|---|---|
| прибрати `dependencies=[AdminDep]` з `DELETE /api/news` | `8 failed, 19 passed` у `test_admin_api.py` |
| прибрати `nx=True` у `remember_delivery` | `2 failed, 277 passed`: `test_replay_is_409` в unit і integration |
| `max_redirects=0` у фікстурі `local_policy` | `1 failed, 13 passed` у `test_sources_ssrf.py` — розбір у [контрольній точці](checkpoint.md#modify) |
| `hmac.compare_digest(...)` → `signature != sign(...)` | **`279 passed`** — жоден тест не впав |

Остання поломка не видна тестам: обидва порівняння дають **той самий результат**, різниця лише в **часі**. `!=` зупиняється на першому неспівпадінні, і за часом відповіді підпис можна підбирати по символу. Функціональний тест такого не бачить. Тому правило записано в `CLAUDE.md` кроку для AI-асистента — «Секрети порівнюються `hmac.compare_digest`, не `==`» — і це пункт рецензії коду.

## Запуск { #run }

```text
$ pytest -q
279 passed, 2 deselected in 18.66s
$ pytest -q -m unit
167 passed, 114 deselected in 9.04s
$ mypy --strict news_hub
Success: no issues found in 18 source files
```

`2 deselected` — справжні виклики LLM з кроку 7 (`pytest -m llm`). Ті самі тести на PostgreSQL і справжньому Redis: `TEST_DATABASE_URL=… TEST_REDIS_URL=… pytest` (команда — у [README кроку](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/README.md)).

Нові залежності мають мінімальні версії з причиною:

```text title="requirements.txt (нове)"
PyJWT>=2.4             # крок 8: JWT адміна (2.4 — виправлено підміну алгоритму, CVE-2022-29217)
bcrypt>=4.0            # крок 8: хеш пароля адміна — напряму, без passlib (passlib 1.7.4 не працює з bcrypt 5)
```

## Правило { #rule }

!!! tip "Правило"
    Кожен спосіб обходу — окремий випадок тесту; для SSRF перевіряй, що запит **не дійшов**, а не лише код відповіді. Список публічних маршрутів — явний, а тест порівнює його з усіма маршрутами застосунку. Те, що впливає лише на час (порівняння секретів), тести не бачать — це правило проєкту й пункт рецензії.

**Далі:** [Контрольна точка](checkpoint.md).
