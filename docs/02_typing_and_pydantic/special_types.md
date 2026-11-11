# URL, email і дати: `HttpUrl`, `EmailStr`, `AwareDatetime`

## Проблема { #problem }

Адреса, email і момент часу приходять рядками, але рядком не є. Адреса має схему, хост, порт; у email — домен, який можна перевірити; час без часового поясу — це не момент, а «12:00 десь». Pydantic має для цього типи, які перевіряють формат і дають структурований об'єкт. Цей об'єкт уже не рядок. Він не порівнюється з рядком, не лягає в `json.dumps` і в колонку SQLite. А час із поясом база може зберегти без поясу.

## Ментальна модель { #mental-model }

| Тип | Приймає | Повертає | У JSON Schema |
|---|---|---|---|
| `HttpUrl` | лише `http`/`https`, з хостом; до 2083 символів | об'єкт `HttpUrl` (не `str`): `.scheme`, `.host`, `.port`, `.path`, `.query` | `string`, `format: uri` |
| `AnyUrl` | будь-яку схему: `ftp`, `file`, `redis`… | об'єкт `AnyUrl` | `string`, `format: uri` |
| `EmailStr` | адресу, яку пропускає бібліотека `email-validator` | `str`, з доменом у нижньому регістрі | `string`, `format: email` |
| `datetime` | ISO 8601 з поясом або без, Unix-час | `datetime`, aware або naive — як прийшло | `string`, `format: date-time` |
| `AwareDatetime` | лише з поясом (`Z`, `+02:00`) або Unix-час | aware `datetime` | так само |
| `NaiveDatetime` | лише без поясу | naive `datetime` | так само |

`EmailStr` потребує окремого пакета: `pip install "pydantic[email]"` (або `email-validator`).

## `HttpUrl` і `AnyUrl` { #url }

[`examples/pydantic_v2/types_demo.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/pydantic_v2/types_demo.py):

```text
--- 1. HttpUrl і AnyUrl
   'https://Example.COM'                HttpUrl: https://example.com/                   (HttpUrl)
                                        AnyUrl:  https://example.com/                   (AnyUrl)
   'https://example.com/a b?q=1#top'    HttpUrl: https://example.com/a%20b?q=1#top      (HttpUrl)
                                        AnyUrl:  https://example.com/a%20b?q=1#top      (AnyUrl)
   'http://127.0.0.1:8080/admin'        HttpUrl: http://127.0.0.1:8080/admin            (HttpUrl)
                                        AnyUrl:  http://127.0.0.1:8080/admin            (AnyUrl)
   'http://user:pass@example.com'       HttpUrl: http://user:pass@example.com/          (HttpUrl)
                                        AnyUrl:  http://user:pass@example.com/          (AnyUrl)
   'ftp://example.com/file'             HttpUrl: ✗ url_scheme: URL scheme should be 'http' or 'https'
                                        AnyUrl:  ftp://example.com/file                 (AnyUrl)
   'file:///etc/passwd'                 HttpUrl: ✗ url_scheme: URL scheme should be 'http' or 'https'
                                        AnyUrl:  file:///etc/passwd                     (AnyUrl)
   'not-a-valid-url'                    HttpUrl: ✗ url_parsing: Input should be a valid URL, relative URL without a base
                                        AnyUrl:  ✗ url_parsing: Input should be a valid URL, relative URL without a base
   'https://пример.укр/'                HttpUrl: https://xn--e1afmkfd.xn--j1amh/        (HttpUrl)
                                        AnyUrl:  https://xn--e1afmkfd.xn--j1amh/        (AnyUrl)
```

**Адресу нормалізовано**: хост у нижньому регістрі, `/` після хоста, пробіл → `%20`, кириличний домен → punycode. `str(url)` може не збігатися з тим, що надіслав клієнт. Це важливо, якщо адреса — ключ унікальності в базі: `https://Example.COM` і `https://example.com/` стануть однаковими, і це добре. Але порівнювати треба вже нормалізовані адреси.

**`HttpUrl` перевіряє формат, а не безпеку.** `http://127.0.0.1:8080/admin` і `user:pass@` пройшли. Якщо сервер сам завантажує адресу від клієнта, `HttpUrl` від SSRF не захищає: потрібна перевірка хоста й IP після DNS (у News Hub — `safe_fetch.py`, [крок 8](../tutorials/08_security/index.md)). `AnyUrl` пропускає ще й `file://` — для адрес від користувача він не підходить.

## Що повертає `HttpUrl` { #url-object }

```text
--- 2. що всередині HttpUrl
   isinstance(url, str)=False scheme=https host=www.rbc.ua port=443 path=/ukr/news/x.html query=utm=1
   url == 'https://www.rbc.ua/ukr/news/x.html?utm=1': False | str(url) == ...: True
```

- **Не рядок.** У Pydantic 2.0–2.9 це був `pydantic_core.Url`, з 2.10 — клас `pydantic.networks.HttpUrl`. У Pydantic 1 `HttpUrl` був підкласом `str`, тож код міграції, що робив `url.startswith(...)`, ламається.
- **Частини адреси — готові атрибути**: `url.host`, `url.port` (443 для https, навіть якщо не вказано). Тому валідатори News Hub перевіряють `url.host`, а не рядок.
- **`url == "https://..."` — завжди `False`**, навіть для тієї самої адреси. Порівнюй `str(url)`.

## Серіалізація і база { #serialize }

```text
--- 3. серіалізація
   model_dump(): {'url': HttpUrl('https://example.com/')}
   model_dump(mode='json'): {'url': 'https://example.com/'}
   json.dumps(model_dump()): Object of type HttpUrl is not JSON serializable
   json.dumps(..., default=str): {"url": "https://example.com/"}
--- 4. у базу
   website=link.url: ProgrammingError (sqlite3.ProgrammingError) Error binding parameter 1: type 'HttpUrl' is not supported
   website=str(link.url): 'https://example.com/'; created_at з SQLite: datetime.datetime(2026, 11, 11, 12, 0)
```

| Куди | Як |
|---|---|
| відповідь FastAPI | нічого робити не треба — FastAPI перетворить сам |
| словник для JSON (Redis, черга) | `model_dump(mode="json")` або `model_dump_json()` |
| колонка бази | `str(url)` — драйвер не знає типу `HttpUrl` |
| у коді, що чекає рядок (`httpx.get`, логування) | `str(url)` |

**SQLite губить часовий пояс.** `DateTime(timezone=True)` у SQLite зберігає рядок без поясу. Записали `12:00+02:00` — прочитали naive `12:00`, і вже не відомо, чи це 12:00 за Києвом, чи за UTC. PostgreSQL (`timestamptz`) зберігає момент і повертає aware `datetime` в UTC.

## `EmailStr` { #email }

```text
--- 5. EmailStr
   'Olena@Example.COM'      Olena@example.com                      (str)
   'olena@localhost'        ✗ value_error: value is not a valid email address: The part after the @-sig
   'not-an-email'           ✗ value_error: value is not a valid email address: An email address must ha
   'olena.@example.com'     ✗ value_error: value is not a valid email address: An email address cannot 
   'олена@приклад.укр'      олена@приклад.укр                      (str)
```

- Повертає звичайний `str`, на відміну від `HttpUrl`.
- **Домен — у нижньому регістрі, а частина до `@` — як була.** Для унікальності користувачів цього мало: `Olena@example.com` і `olena@example.com` — різні рядки. Зазвичай email зберігають у нижньому регістрі цілком і порівнюють так само.
- `localhost` і інші службові домени відхиляються. Кириличні адреси приймаються.
- Тип помилки — загальний `value_error`, а не окремий код.
- `EmailStr` перевіряє формат, а не те, що поштова скринька існує. Це перевіряє лише лист із підтвердженням.

## `datetime`, `AwareDatetime`, `NaiveDatetime` { #datetime }

```text
--- 6. datetime, AwareDatetime, NaiveDatetime
   '2026-11-11T12:00:00+02:00'  datetime: 2026-11-11 12:00:00+02:00              (datetime)
                                Aware:    2026-11-11 12:00:00+02:00              (datetime)
                                Naive:    ✗ timezone_naive: Input should not have timezone info
   '2026-11-11T12:00:00Z'       datetime: 2026-11-11 12:00:00+00:00              (datetime)
                                Aware:    2026-11-11 12:00:00+00:00              (datetime)
                                Naive:    ✗ timezone_naive: Input should not have timezone info
   '2026-11-11T12:00:00'        datetime: 2026-11-11 12:00:00                    (datetime)
                                Aware:    ✗ timezone_aware: Input should have timezone info
                                Naive:    2026-11-11 12:00:00                    (datetime)
   1700000000                   datetime: 2023-11-14 22:13:20+00:00              (datetime)
                                Aware:    2023-11-14 22:13:20+00:00              (datetime)
                                Naive:    ✗ timezone_naive: Input should not have timezone info
```

- **`datetime` приймає обидва варіанти**, і в коді змішуються aware і naive. Порівняння таких значень — `TypeError: can't compare offset-naive and offset-aware datetimes`.
- **`AwareDatetime` на вході** змушує клієнта вказати пояс. Unix-час — завжди UTC, тож проходить.
- Пояс зберігається як прийшов (`+02:00`). Перед записом і порівнянням зручно привести до UTC: `value.astimezone(timezone.utc)`.

## `AwareDatetime` у відповіді, SQLite у базі { #aware-response }

```text
--- 7. AwareDatetime у відповіді, а в базі SQLite
   500 Internal Server Error
   OpenAPI: {'type': 'string', 'maxLength': 2083, 'minLength': 1, 'format': 'uri', 'title': 'Website'} {'type': 'string', 'format': 'date-time', 'title': 'Created At'}
```

Модель відповіді з `created_at: AwareDatetime` отримала з SQLite naive `datetime` → `ResponseValidationError` → `500`. На PostgreSQL той самий код працює. Тому News Hub у `NewsOut` пише `scraped_at: datetime`, а не `AwareDatetime`: тести йдуть на SQLite, продакшн — на PostgreSQL, і відповідь має працювати з обома.

## У News Hub { #news-hub }

| Тип | Де | Як |
|---|---|---|
| `HttpUrl` | `NewsItem.url` ([крок 1](../tutorials/01_typing_pydantic/index.md)), `ScrapeRequest.pages` | валідатори перевіряють `url.host`; у базу — `str(item.url)` у `repository.py` |
| `DateTime(timezone=True)` | `scraped_at`, `analyzed_at`, `created_at` у `tables.py` ([крок 3](../tutorials/03_sqlalchemy_alembic/index.md)) | PostgreSQL `timestamptz`; значення ставить база (`server_default=func.now()`) |
| `datetime` у відповіді | `NewsOut.scraped_at` | приймає і aware (PostgreSQL), і naive (SQLite у тестах) |
| `str` + `max_length` для адреси джерела | `SourceCreate.url` ([крок 8](../tutorials/08_security/index.md)) | перевірка — у `safe_fetch.py`: схема, хост, приватні IP після DNS |

## Типові помилки { #mistakes }

| Помилка | Наслідок | Як правильно |
|---|---|---|
| `HttpUrl` у колонку бази | `ProgrammingError: type 'HttpUrl' is not supported` | `str(url)` |
| `url == "https://..."` | завжди `False` | `str(url) == ...` |
| `url.startswith(...)` після міграції з Pydantic 1 | `AttributeError` | `str(url).startswith(...)` або `url.scheme`/`url.host` |
| `json.dumps(model.model_dump())` | `TypeError` на `HttpUrl`, `datetime` | `model_dump(mode="json")` |
| `HttpUrl` як захист від SSRF | `http://127.0.0.1/admin`, `http://169.254.169.254/` проходять | перевірка хоста й IP після DNS |
| `AnyUrl` для адрес від користувача | `file:///etc/passwd` проходить | `HttpUrl` + перевірка хоста |
| `EmailStr` без `email-validator` | `ImportError` під час оголошення моделі | `pip install "pydantic[email]"` |
| email як ключ унікальності без нормалізації | два акаунти `Olena@…` і `olena@…` | зберігати в нижньому регістрі |
| `AwareDatetime` у моделі відповіді з SQLite | `500` | `datetime` у відповіді, або тести на PostgreSQL |
| `datetime` на вході для часу подій | «12:00» без поясу трактується як час сервера | `AwareDatetime` на вході, UTC у базі |

## Безпека { #security }

- **Валідація формату не дорівнює перевірці довіри.** `HttpUrl` не відрізняє `https://bank.example` від `https://bank.example.evil.com`. Для редиректів і завантажень — список дозволених хостів, порівняння `url.host`, а не підрядка.
- **`user:pass@` в адресі** — облікові дані, які потраплять у журнали. Якщо вони не потрібні, відхиляй адреси з `url.username`.
- **Нормалізація допомагає**: перевіряй уже нормалізований `url.host` (у нижньому регістрі, punycode), а не рядок від клієнта. Інакше `EXAMPLE.com` чи кириличний двійник домену обійдуть порівняння.
- **Час без поясу — джерело помилок у терміні дії**: токен, що «спливає о 12:00», спливе на дві години раніше чи пізніше залежно від поясу сервера.

## Питання { #questions }

1. Що повертає `HttpUrl` у Pydantic 2.13? А в Pydantic 1?
2. Чому `url == "https://example.com/"` дає `False`?
3. Як зберегти `HttpUrl` у колонку `String` бази?
4. Чи захищає `HttpUrl` від SSRF? Чому?
5. Що станеться з `created_at: AwareDatetime` у моделі відповіді, якщо база — SQLite?
6. Чим `AwareDatetime` відрізняється від `datetime` на вході?
7. Що `EmailStr` змінює в адресі, а що лишає?

??? success "Відповіді"

    1. Об'єкт класу `HttpUrl` з атрибутами `scheme`, `host`, `port`, `path`, `query` (до 2.10 — `pydantic_core.Url`); у Pydantic 1 — підклас `str`.
    2. Об'єкт `HttpUrl` не дорівнює рядку; порівнювати треба `str(url)`.
    3. `str(url)`.
    4. Ні: перевіряє лише схему й формат; `127.0.0.1`, приватні й службові адреси проходять.
    5. SQLite поверне naive `datetime`, перевірка відповіді впаде, клієнт отримає `500`.
    6. `datetime` приймає час і з поясом, і без; `AwareDatetime` вимагає пояс (або Unix-час).
    7. Домен переводить у нижній регістр; частину до `@` лишає як є.

## Що далі { #next }

[Частина II. Типи і Pydantic](README.md) — решта розділів частини.

**Джерела:** Pydantic — [Network Types](https://docs.pydantic.dev/latest/api/networks/), [Pydantic Types — AwareDatetime, NaiveDatetime](https://docs.pydantic.dev/latest/api/types/#pydantic.types.AwareDatetime), [Standard Library Types — datetime](https://docs.pydantic.dev/latest/api/standard_library_types/#datetimedatetime), [Changelog v2.10](https://github.com/pydantic/pydantic/releases/tag/v2.10.0); [email-validator](https://github.com/JoshData/python-email-validator); [SQLAlchemy — DateTime](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.DateTime); [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
