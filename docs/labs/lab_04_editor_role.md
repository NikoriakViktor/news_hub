# Лаба 4. Роль редактора { #lab-04 }

| | |
|---|---|
| Основа | [крок 8](../tutorials/08_security/index.md) — `steps/08_security` |
| Що тренує | авторизація за роллю в JWT, 401 проти 403, залежність FastAPI як правило доступу, тест-охоронець, що змушує ухвалити рішення для кожного ендпоінта |
| Складність | ★★☆ |
| Орієнтовний час | 2–3 години |

## Мета { #goal }

**Задача.** У [кроці 8](../tutorials/08_security/admin_jwt.md) є один обліковий запис, адмін. Він робить усе: правує заголовки, запускає аналіз LLM, видаляє новини, додає RSS-джерела. Редакції потрібна людина, яка виправляє заголовки й запускає аналіз. Видаляти новини, чистити базу, запускати збір і додавати чужі URL ця людина не повинна. Пароль адміна давати їй не можна.

**Зміна.** Друга роль, `editor`, з окремим ім'ям і хешем пароля в середовищі. Роль пишеться в той самий JWT (поле `role` там уже є). Нова залежність `require_editor` пропускає `editor` і `admin`, а `require_admin` лишається тільки для адміна.

**Результат.**

| Хто | Читання | `POST /api/news`, `PATCH /api/news/{id}`, `POST /api/news/{id}/analyze` | Решта запису (видалення, збір, джерела, задачі) |
|---|---|---|---|
| без токена | так | `401` | `401` |
| `editor` | так | так | `403` |
| `admin` | так | так | так |
| підписаний токен з невідомою роллю | так | `403` | `403` |
| токен без `role`, підроблений чи прострочений | так | `401` | `401` |

**Правило.** `401` означає «я не знаю, хто ти»: токена немає або він недійсний. `403` означає «я знаю, хто ти, але тобі не можна». Невідома роль у токені з правильним підписом — це `403`, а не доступ «за замовчуванням». Список дозволеного для ролі записаний у тесті, тому новий ендпоінт не отримає доступ редактора випадково.

## Звідки починаємо { #start }

```bash
cp -r steps/08_security lab_04 && cd lab_04
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

```text
294 passed, 2 deselected in 10.25s
```

Перечитайте [`news_hub/security.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/news_hub/security.py) (`require_admin`, `decode_token` з `require: ["exp", "sub", "role"]`, `LoginGuard`), вхід `admin_token` у [`news_hub/api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/news_hub/api.py) (лічильник невдач на ім'я, bcrypt у `run_in_threadpool`, `Cache-Control: no-store`) і [`tests/integration/test_admin_api.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/08_security/tests/integration/test_admin_api.py): там `test_every_other_endpoint_requires_admin` обходить усі маршрути й шукає `require_admin` у залежностях.

## Вимоги { #requirements }

1. **Налаштування.** `AdminSettings` отримує `editor_username: str | None` і `editor_password_hash: str | None` зі змінних `EDITOR_USERNAME` і `EDITOR_PASSWORD_HASH`. Редактора може й не бути: без цих змінних усе працює як раніше. `EDITOR_USERNAME` без bcrypt-хешу дає `RuntimeError` при старті, з назвою змінної в повідомленні, як для адміна.
2. **Вхід.** `POST /api/admin/token` визначає, чия це пара «ім'я + пароль», і видає токен з `role="admin"` або `role="editor"`. Неправильна пара дає `401` з тим самим текстом, що й зараз. Пароль редактора з іменем адміна не підходить. Захист входу кроку 8 лишається для обох ролей: ліміт спроб з однієї адреси (middleware), `LoginGuard` на ім'я (після `LOGIN_FAIL_LIMIT` невдач — `429`, і для адміна лічильник окремий), перевірка пароля в `run_in_threadpool`, `Cache-Control: no-store` на відповіді з токеном. Окремий ендпоінт входу для редактора без цих захистів — не розв'язок.
3. **Токен.** `create_access_token(settings, subject, now=None, *, role="admin")`. Старі виклики з conftest працюють без змін.
4. **Залежності.** `require_editor` дає `401` для того самого, що й `require_admin` (спільний код винесіть в одну функцію). Роль, що не входить до `admin`/`editor`, дає `403` «потрібні права редактора». `EditorDep = Depends(require_editor)`.
5. **Ендпоінти.** `EditorDep` отримують рівно три: `POST /api/news`, `PATCH /api/news/{news_id}`, `POST /api/news/{news_id}/analyze`. Решта захищених лишаються з `AdminDep`.
6. **Тест-охоронець.** Після зміни `test_every_other_endpoint_requires_admin` впаде: три ендпоінти більше не мають `require_admin`. Так і має бути, тест змушує ухвалити рішення. Оновіть у ньому `admin_protected`, щоб він приймав і `require_editor`. Це **єдина** дозволена зміна наявних тестів.

## Критерії приймання { #acceptance }

```python title="tests/integration/test_roles.py"
"""Лаба 4: дві ролі. Редактор правує й аналізує новини; видаляє, збирає й керує джерелами — лише адмін."""
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from news_hub.api import app
from news_hub.llm import FakeLLM
from news_hub.middleware import LIMITS
from news_hub.security import (LOGIN_FAIL_LIMIT, create_access_token, hash_password, load_admin_settings,
                               require_admin, require_editor)

from .conftest import ADMIN_PASSWORD

EDITOR_PASSWORD = "test-editor-password"
NEWS = {"title": "Нацбанк знизив облікову ставку до 13%", "url": "https://www.rbc.ua/ukr/news/nbu-rate-1.html"}

# Що може редактор (крім читання). Решта захищених ендпоінтів — лише адмін.
EDITOR = {("POST", "/api/news"), ("PATCH", "/api/news/{news_id}"), ("POST", "/api/news/{news_id}/analyze")}


@pytest.fixture(autouse=True)
def editor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """До старту застосунку (autouse-фікстури — першими): обліковий запис редактора в середовищі."""
    monkeypatch.setenv("EDITOR_USERNAME", "olena")
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", hash_password(EDITOR_PASSWORD, rounds=4))


def token(role: str, subject: str = "olena") -> dict[str, str]:
    settings = load_admin_settings()
    assert settings is not None
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "role": role, "iat": now, "exp": now + timedelta(minutes=5)}
    return {"Authorization": f"Bearer {jwt.encode(payload, settings.jwt_secret, algorithm='HS256')}"}


@pytest.fixture
def editor(anon: TestClient) -> Iterator[TestClient]:
    anon.headers.update(token("editor"))
    yield anon


@pytest.fixture
def admin_auth() -> dict[str, str]:
    return token("admin", subject="admin")


def news_id(client: TestClient) -> int:
    created: int = client.post("/api/news", json=NEWS).json()["id"]
    return created


def required_role(route: APIRoute) -> str | None:
    stack = list(route.dependant.dependencies)
    while stack:
        dependency = stack.pop()
        if dependency.call is require_admin:
            return "admin"
        if dependency.call is require_editor:
            return "editor"
        stack.extend(dependency.dependencies)
    return None


def test_editor_endpoints_are_exactly_the_agreed_ones() -> None:
    editor_routes = {(method, route.path) for route in app.routes if isinstance(route, APIRoute)
                     for method in route.methods if required_role(route) == "editor"}
    assert editor_routes == EDITOR


def test_editor_logs_in_and_gets_editor_token(anon: TestClient) -> None:
    response = anon.post("/api/admin/token", json={"username": "olena", "password": EDITOR_PASSWORD})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"                 # як і токен адміна
    settings = load_admin_settings()
    assert settings is not None
    payload = jwt.decode(response.json()["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert (payload["sub"], payload["role"]) == ("olena", "editor")


def test_admin_login_still_gives_admin_role(anon: TestClient) -> None:
    response = anon.post("/api/admin/token", json={"username": "admin", "password": ADMIN_PASSWORD})
    settings = load_admin_settings()
    assert settings is not None
    assert jwt.decode(response.json()["access_token"], settings.jwt_secret, algorithms=["HS256"])["role"] == "admin"


@pytest.mark.parametrize(("username", "password"), [("olena", "wrong"), ("admin", EDITOR_PASSWORD)])
def test_wrong_pair_is_401(anon: TestClient, username: str, password: str) -> None:
    """Пароль редактора не підходить до імені адміна — ролі не змішуються."""
    response = anon.post("/api/admin/token", json={"username": username, "password": password})
    assert response.status_code == 401


def test_editor_login_is_locked_per_name_like_admin(anon: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Вхід редактора — той самий ендпоінт, отже й той самий LoginGuard: невдачі рахуються на ім'я."""
    monkeypatch.setitem(LIMITS, "login", (1000, 300))                     # зняти ліміт на адресу, як у test_admin_api
    codes = [anon.post("/api/admin/token", json={"username": "olena", "password": f"guess-{i}"}).status_code
             for i in range(LOGIN_FAIL_LIMIT)]
    assert codes == [401] * LOGIN_FAIL_LIMIT
    locked = anon.post("/api/admin/token", json={"username": "olena", "password": EDITOR_PASSWORD})
    assert locked.status_code == 429 and "під цим іменем" in locked.json()["detail"]
    admin = anon.post("/api/admin/token", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert admin.status_code == 200                                         # адміна підбір пароля редактора не закрив


def test_editor_creates_patches_and_analyzes(editor: TestClient, fake_llm: FakeLLM) -> None:
    created = editor.post("/api/news", json=NEWS)
    assert created.status_code == 201
    nid = created.json()["id"]
    assert editor.patch(f"/api/news/{nid}", json={"title": "Нацбанк знизив облікову ставку"}).status_code == 200
    fake_llm.replies.append('{"summary": "НБУ знизив ставку.", "category": "Економіка", '
                            '"sentiment": "позитивна", "keywords": ["НБУ"]}')
    assert editor.post(f"/api/news/{nid}/analyze").status_code == 200


@pytest.mark.parametrize(("method", "path", "body"), [
    ("DELETE", "/api/news/{id}", None),
    ("DELETE", "/api/news", None),
    ("POST", "/api/scrape", {"source": "snapshot"}),
    ("POST", "/api/sources", {"url": "https://www.pravda.com.ua/rss/", "name": "УП"}),
    ("GET", "/api/sources", None),
])
def test_editor_cannot_do_admin_things(editor: TestClient, method: str, path: str, body: dict[str, str] | None) -> None:
    nid = news_id(editor)
    response = editor.request(method, path.format(id=nid), json=body)
    assert response.status_code == 403
    assert response.json()["detail"] == "потрібні права адміністратора"
    assert editor.get(f"/api/news/{nid}").status_code == 200              # новина на місці


def test_admin_still_can_everything(anon: TestClient, admin_auth: dict[str, str]) -> None:
    anon.headers.update(admin_auth)
    nid = news_id(anon)
    assert anon.patch(f"/api/news/{nid}", json={"title": "Нацбанк знизив облікову ставку"}).status_code == 200
    assert anon.delete(f"/api/news/{nid}").status_code == 204


@pytest.mark.parametrize(("headers", "status"), [
    ({}, 401),                                                              # без токена
    ({"Authorization": "Bearer not-a-jwt"}, 401),                           # сміття
    (None, 401),                                                            # без поля role → недійсний
    ("superuser", 403),                                                     # справжній підпис, невідома роль
    ("reader", 403),
])
def test_patch_without_editor_rights(anon: TestClient, admin_auth: dict[str, str],
                                     headers: dict[str, str] | str | None, status: int) -> None:
    created = anon.post("/api/news", json=NEWS, headers=admin_auth).json()["id"]
    if headers is None:
        settings = load_admin_settings()
        assert settings is not None
        no_role = jwt.encode({"sub": "olena", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                             settings.jwt_secret, algorithm="HS256")
        headers = {"Authorization": f"Bearer {no_role}"}
    elif isinstance(headers, str):
        headers = token(headers)
    response = anon.patch(f"/api/news/{created}", json={"title": "Чужа правка заголовка"}, headers=headers)
    assert response.status_code == status


def test_create_access_token_takes_role() -> None:
    settings = load_admin_settings()
    assert settings is not None
    encoded = create_access_token(settings, "olena", role="editor")
    assert jwt.decode(encoded, settings.jwt_secret, algorithms=["HS256"])["role"] == "editor"


def test_editor_is_optional_but_not_half_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDITOR_USERNAME")
    monkeypatch.delenv("EDITOR_PASSWORD_HASH")
    settings = load_admin_settings()
    assert settings is not None and settings.editor_username is None
    monkeypatch.setenv("EDITOR_USERNAME", "olena")
    monkeypatch.setenv("EDITOR_PASSWORD_HASH", "plain-password")
    with pytest.raises(RuntimeError, match="EDITOR_PASSWORD_HASH"):
        load_admin_settings()
```

Фікстура `editor_env` має `autouse=True` не для зручності. Налаштування читаються в `lifespan` під час старту `TestClient`, тобто у фікстурі `anon`. Autouse-фікстури виконуються першими, тож змінні середовища вже задані, коли застосунок стартує.

`test_editor_login_is_locked_per_name_like_admin` знімає ліміт на адресу так само, як `test_login_lockout_counts_failures_per_name_from_any_address` у кроці: усі спроби в тесті йдуть з однієї адреси `testclient`, а перевіряється саме лічильник на ім'я.

**До змін** `require_editor` немає, тест не збирається:

```text
E   ImportError: cannot import name 'require_editor' from 'news_hub.security' (…/news_hub/security.py)
=========================== short test summary info ============================
ERROR tests/integration/test_roles.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.15s
```

**Після зміни коду, але до оновлення охоронця** (вимога 6):

```text
E         Extra items in the left set:
E         ('POST', '/api/news/{news_id}/analyze')
E         ('POST', '/api/news')
E         ('PATCH', '/api/news/{news_id}')
FAILED tests/integration/test_admin_api.py::test_every_other_endpoint_requires_admin
1 failed, 313 passed, 2 deselected in 9.60s
```

**Після** еталонного розв'язку:

```text
$ pytest -q
314 passed, 2 deselected in 10.61s
$ mypy --strict news_hub
Success: no issues found in 18 source files
```

## Підказки { #hints }

??? tip "Одна перевірка токена на дві ролі"

    Усе, що дає `401` (немає заголовка, `ExpiredSignatureError`, `InvalidTokenError`, нема `role`), винесіть у `_verified_payload(settings, credentials) -> dict[str, Any]`. Тоді `require_admin` і `require_editor` відрізняються одним рядком: якою множиною ролей перевіряють `payload["role"]`.

??? tip "Чому не `Depends(require_role("editor"))`"

    Фабрика залежностей теж підходить, але кожен її виклик створює **нову** функцію. Тоді тест-охоронець не зможе знайти правило через `dependency.call is …`. Дві іменовані функції легше знайти і в тестах, і в `/docs`.

??? tip "Час відповіді на вході"

    `authenticate` навмисно перевіряє пароль адміна завжди, навіть для чужого імені. Зберіть цю властивість: спершу `authenticate(...)` для адміна, потім, якщо редактора налаштовано, `hmac.compare_digest` для імені й `verify_password` для пароля редактора.

    Тепер на вході можуть виконатися **два** bcrypt (адміна й редактора), тож `authenticate_role` тим паче має йти через `await run_in_threadpool(...)`, як `authenticate` у кроці: інакше кожна спроба входу зупиняє цикл подій для всіх запитів.

??? tip "`LoginGuard` уже рахує й редактора"

    Не чіпайте `LoginGuard`: він рахує невдачі на **ім'я**, а не на роль. Досить, щоб вхід редактора йшов тим самим `admin_token`: `guard.retry_after(...)` до перевірки пароля, `guard.failed(...)` на `401`, `guard.succeeded(...)` після успіху.

## Підхід до розв'язку { #solution }

??? success "Підхід до розв'язку"

    `news_hub/security.py`, ключові частини:

    ```python
    Role = Literal["admin", "editor"]


    @dataclass(frozen=True)
    class AdminSettings:
        jwt_secret: str
        username: str
        password_hash: str
        expire_minutes: int = 30
        editor_username: str | None = None          # редактора може й не бути
        editor_password_hash: str | None = None

    # load_admin_settings — після перевірок адміна:
        editor_username = env.get("EDITOR_USERNAME") or None
        editor_hash = env.get("EDITOR_PASSWORD_HASH") or None
        if editor_username and not (editor_hash or "").startswith("$2"):
            raise RuntimeError("EDITOR_PASSWORD_HASH — bcrypt-хеш ($2b$…), а не пароль; "
                               "згенеруй: python -m news_hub.security")


    def authenticate_role(settings: AdminSettings, username: str, password: str) -> Role | None:
        if authenticate(settings, username, password):
            return "admin"
        if settings.editor_username and settings.editor_password_hash:
            name_ok = hmac.compare_digest(username.encode(), settings.editor_username.encode())
            password_ok = verify_password(password, settings.editor_password_hash)
            if name_ok and password_ok:
                return "editor"
        return None


    def create_access_token(settings: AdminSettings, subject: str, now: datetime | None = None,
                            *, role: Role = "admin") -> str:
        now = now or datetime.now(timezone.utc)
        payload = {"sub": subject, "role": role, "iat": now,
                   "exp": now + timedelta(minutes=settings.expire_minutes)}
        return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


    CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


    def _verified_payload(settings: AdminSettings, credentials: HTTPAuthorizationCredentials | None) -> dict[str, Any]:
        """401 — немає токена, підроблений, прострочений або без обов'язкових полів (sub, role, exp)."""
        if credentials is None:
            raise _unauthorized("потрібен токен: Authorization: Bearer <access_token>")
        try:
            payload = decode_token(settings, credentials.credentials)
        except jwt.ExpiredSignatureError as error:
            raise _unauthorized("токен прострочений") from error
        except jwt.InvalidTokenError as error:
            raise _unauthorized("недійсний токен") from error
        return payload


    def require_admin(settings: AdminSettingsDep, credentials: CredentialsDep) -> str:
        payload = _verified_payload(settings, credentials)
        if payload["role"] != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="потрібні права адміністратора")
        subject: str = payload["sub"]
        return subject


    def require_editor(settings: AdminSettingsDep, credentials: CredentialsDep) -> str:
        payload = _verified_payload(settings, credentials)
        if payload["role"] not in ("admin", "editor"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="потрібні права редактора")
        subject: str = payload["sub"]
        return subject


    AdminDep = Depends(require_admin)
    EditorDep = Depends(require_editor)
    ```

    `news_hub/api.py`: у трьох декораторах `dependencies=[AdminDep]` → `dependencies=[EditorDep]`, імпорт `authenticate_role` і `EditorDep` замість `authenticate`, а у вході змінюються три рядки (`LoginGuard`, `no-store` — як були):

    ```python
        guard = LoginGuard(redis)
        wait = await guard.retry_after(body.username)
        if wait:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": str(wait)},
                                detail=f"забагато невдалих входів під цим іменем; спробуй через {wait} с")
        role = await run_in_threadpool(authenticate_role, settings, body.username, body.password)
        if role is None:
            await guard.failed(body.username)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="неправильне ім'я або пароль")
        await guard.succeeded(body.username)
        response.headers["Cache-Control"] = "no-store"           # токен не кешують ні браузер, ні проксі
        return TokenResponse(access_token=create_access_token(settings, body.username, role=role),
                             expires_in=settings.expire_minutes * 60)
    ```

    `tests/integration/test_admin_api.py`, одна зміна в `admin_protected` (і `require_editor` в імпорті):

    ```python
            if dependency.call in (require_admin, require_editor):     # редактор — теж за токеном
                return True
    ```

## Що перевірити самому { #self-check }

- Замініть у `require_editor` перевірку ролі на `if False:` (пропускати будь-який справжній токен). Які тести впадуть? В еталонному прогоні червоніють рівно два: `test_patch_without_editor_rights[superuser-403]` і `[reader-403]`.
- 20 невдалих спроб під іменем редактора закривають вхід **редактору** на `LOGIN_FAIL_WINDOW` секунд, а адмін входить далі (так перевіряє `test_editor_login_is_locked_per_name_like_admin`). Чому лічильник на ім'я, а не на роль? Що атакувальник може зробити зі справжнім редактором, знаючи лише його ім'я?
- Видайте редактору токен на 30 днів і звільніть його через тиждень. Що з цим токеном, поки він не прострочиться? Що в News Hub довелося б змінити, щоб відкликати токен одразу (ідеї: короткий `exp` + refresh, список відкликаних `jti` у Redis)?
- `sub` редактора записано в токені, але ніде не використовується. Як записати в базу, **хто** змінив заголовок (стовпець `updated_by`, нова міграція), і чому `sub` треба брати з токена, а не з тіла запиту?
- У `/docs` обидві залежності показані тим самим замком `HTTPBearer`. Як з документації дізнатися, якої ролі вимагає ендпоінт? Підказка: `description` або `responses={403: …}` у декораторі.
