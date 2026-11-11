# Контрольна точка: крок 1

## Перевір, що крок робочий { #check }

З папки `steps/01_typing_pydantic`:

```text
$ pytest -q -p no:cacheprovider
............                                                             [100%]
12 passed in 0.13s
$ mypy --strict news_hub
Success: no issues found in 4 source files
$ python -c "from news_hub.snapshot import load_snapshot; from news_hub.models import validate_news; print([len(x) for x in validate_news(load_snapshot())])"
[168, 0]
```

12 тестів: 10 — модель і `validate_news` (поля з URL, піддомен, порожній час, чотири неправильні значення, `frozen`, відхилені, увесь знімок), 2 — обидві стратегії парсера. Час виконання залежить від машини.

## Чекліст { #checklist }

- [ ] `pytest -q` → `12 passed`, `mypy --strict news_hub` → `Success: no issues found in 4 source files`.
- [ ] `mypy examples/before_dict.py` мовчить, а `mypy examples/after_typed.py` знаходить 2 помилки — і ти можеш пояснити чому.
- [ ] `NewsItem.from_raw(...)` для новини з `auto.rbc.ua` дає `source='auto.rbc.ua'`, `lang='ru'`, `category='Новини'`.
- [ ] Зіпсована новина (`"Коротко"`, `example.com`, `25:99`) дає **одну** `ValidationError` з трьома помилками.
- [ ] `validate_news(load_snapshot())` → 168 перевірених, 0 відхилених; без часу публікації — 31.
- [ ] Можеш пояснити, навіщо `model_validator(mode="before")`, а не `mode="after"`.
- [ ] Можеш пояснити, що перевіряє `mypy`, а що Pydantic, і чому потрібні обидва.

## Типові помилки { #mistakes }

| Симптом | Причина | Що зробити |
|---|---|---|
| `ModuleNotFoundError: No module named 'news_hub'` | скрипт запущено не з папки кроку, або `python шлях/до/script.py` (у `sys.path` потрапляє папка скрипта, а не поточна) | працюй з `steps/01_typing_pydantic`: Python-консоль, `python -c "…"` або `pytest` (у `pytest.ini` є `pythonpath = .`) |
| `PydanticUserError: Please use typing_extensions.TypedDict instead of typing.TypedDict on Python < 3.12.` | `TypedDict` імпортовано з `typing` на Python 3.10–3.11 | `from typing_extensions import TypedDict`, як у `parser.py` |
| `error: Item "None" of "time \| None" has no attribute "hour"  [union-attr]` | `published_time` може бути `None` (31 новина знімка) | спершу `if item.published_time is not None:` |
| `error: Missing type arguments for generic type "dict"  [type-arg]` | `mypy --strict` не приймає «голий» `dict` | `dict[str, str]` або, краще, `TypedDict` |
| `Instance is frozen` | присвоєння полю моделі з `frozen=True` | створи нову модель; `model_copy(update={...})` теж працює, але **не перевіряє** нові значення |
| `TypeError: Object of type HttpUrl is not JSON serializable` | `json.dumps(item.model_dump())` | `item.model_dump(mode="json")` або `item.model_dump_json()` |
| `lang: Field required` для `https://www.rbc.ua/eng/news/…` | `derive_from_url` знає лише `/ukr/` і `/rus/` (`LANGS`), тож `lang` не виведено | так і задумано: модель приймає лише `uk`/`ru`; як розширити — [Зміни приклад](#modify) |

## Практика { #practice }

### Розібраний приклад: `model_validator(mode="before")` { #worked-example }

HTML не містить ні мови, ні категорії — але вони є в URL: `https://www.rbc.ua/ukr/news/…`. `derive_from_url` отримує **сирий** словник до перевірки полів і доповнює його:

1. `urlsplit(url)` ділить URL на частини: `hostname` → `www.rbc.ua`, `path` → `/ukr/news/…`;
2. `source` — домен без `www.`;
3. перша частина шляху → `lang` через `LANGS = {"ukr": "uk", "rus": "ru"}`;
4. друга → `category` через словник `CATEGORIES` з першого прототипу агрегатора;
5. `derived | {…}` — значення, які прийшли непорожніми, мають пріоритет над виведеними.

```python
from news_hub.models import NewsItem

for url in ["https://www.rbc.ua/ukr/news/budget-1.html",
            "https://auto.rbc.ua/rus/news/speka-1778085857.html",
            "https://www.rbc.ua/ukr/economic/hryvnia-2.html"]:
    news = NewsItem.model_validate({"title": "Заголовок для перевірки", "url": url})
    print(news.source, news.lang, news.category)
```

```text
rbc.ua uk Новини
auto.rbc.ua ru Новини
rbc.ua uk Економіка
```

`mode="before"` — бо на цьому етапі полів `source`, `lang`, `category` ще немає: після перевірки полів (`mode="after"`) модель без них просто не створилася б.

А якщо значення передали явно, воно перемагає виведене — і проходить ту саму перевірку типу:

```python
NewsItem.model_validate({"title": "Заголовок для перевірки", "url": "https://www.rbc.ua/ukr/news/x.html", "lang": "en"})
```

```text
1 validation error for NewsItem
lang
  Input should be 'uk' or 'ru' [type=literal_error, input_value='en', input_type=str]
```

### Зміни приклад { #modify }

1. На rbc.ua є й англомовні сторінки (`/eng/news/…`). Додай `"eng": "en"` у `LANGS` і `"en"` у `Literal` поля `lang`. Перевір, що `mypy --strict` не скаржиться, а новина з `/eng/` отримує `lang="en"`.

    Підказка: якщо змінити лише `LANGS`, mypy нагадає про другу половину — анотація `dict[str, Literal["uk", "ru"]]` не пускає нове значення:

    ```text
    news_hub/models.py:21: error: Dict entry 2 has incompatible type "str": "Literal['en']"; expected "str": "Literal['uk', 'ru']"  [dict-item]
    ```

2. Заголовок з одних великих літер — клікбейт. Додай `field_validator("title")`, який відхиляє заголовок, де `title.isupper()`. Допиши тест у `tests/test_models.py`: помилка має бути в полі `title`.

### Спробуй самостійно: модель звіту парсингу { #scrape-report }

Опиши модель `ScrapeReport` — звіт про один збір новин:

- `source: HttpUrl` — яку сторінку парсили;
- `scraped_at: datetime` — коли; за замовчуванням — зараз (`Field(default_factory=…)`);
- `items: list[NewsItem]`, `rejected: list[Rejected]`;
- `@computed_field` `total` — скільки всього новин (перевірених + відхилених).

**Критерії перевірки:** `ScrapeReport(source=…, items=valid, rejected=rejected).model_dump()` містить `total` (для знімка — `168`); неправильний `source` — `ValidationError`; `mypy --strict` чистий.

!!! note "`@computed_field` і mypy"
    `@computed_field` над `@property` mypy не розуміє: `error: Decorators on top of @property are not supported  [prop-decorator]`. Pydantic радить приглушити саме цей код: `@computed_field  # type: ignore[prop-decorator]`. Докладніше про `computed_field` — [у теорії](../../02_typing_and_pydantic/validators.md).

У [кроці 2](../02_fastapi_basics/index.md) `POST /api/scrape` повертає свій `ScrapeReport` — з лічильниками й часом збору замість списків новин. Порівняй його зі своєю моделлю: що зручніше клієнтові API?

### Знайди помилку { #find-bug }

Так визначають категорію новини, розбираючи URL рядком:

```python
url = "https://auto.rbc.ua/rus/news/speka-pislya-holodiv-ryatuemo-vid-rizikiv-1778085857.html"

url_parts = [p for p in url.replace("https://www.rbc.ua", "").split("/") if p]
category_map = {"news": "Новини", "economic": "Економіка", "politics": "Політика"}
raw_cat = url_parts[1] if len(url_parts) > 1 else (url_parts[0] if url_parts else "")
print(url_parts[:3], "→", category_map.get(raw_cat, raw_cat.capitalize() or "Загальні"))
```

```text
['https:', 'auto.rbc.ua', 'rus'] → Auto.rbc.ua
```

URL — справжній, зі знімка. Чому категорія «Auto.rbc.ua»?

??? success "Відповідь"

    `url.replace("https://www.rbc.ua", "")` — розбір URL **рядком**: він працює лише для одного точного домену. Для піддомену `auto.rbc.ua` заміна нічого не прибирає, `split("/")` дає `['https:', 'auto.rbc.ua', 'rus', …]`, і «категорією» стає домен. Помилка тиха — жодного винятку, лише неправильні дані в дашборді.

    `NewsItem` розбирає URL як URL: `urlsplit` окремо дає `hostname` і `path`, тож піддомен ні на що не впливає — див. [розібраний приклад](#worked-example): `auto.rbc.ua ru Новини`. Тест `test_subdomain_is_parsed_not_replaced` закріплює поведінку.

    Правило: структуровані дані (URL, дати, JSON) розбирай бібліотекою, а не `replace`/`split`.

## Підсумок { #summary }

| Поняття | Що запам'ятати |
|---|---|
| Анотації типів | підказки: `def f(x: int) -> str`; Python їх не перевіряє під час роботи |
| `mypy` | перевіряє типи **до запуску**; `--strict` — найсуворіше |
| `X \| None` | змушує обробити `None` |
| `Literal[...]` | лише дозволені значення |
| `TypedDict` | словник з відомими ключами: mypy ловить одруківки; на Python < 3.12 — з `typing_extensions` |
| Pydantic `BaseModel` | перевірка й приведення даних **під час роботи**; помилка — `ValidationError` з усіма полями |
| `Field(...)` | обмеження: `min_length`, `max_length`, `ge`, `le`, `default_factory` |
| `field_validator` / `model_validator` | правило для поля / для всього об'єкта; `mode="before"` — до перевірки полів |
| `model_config` | `str_strip_whitespace`, `frozen` |
| `model_dump()` / `model_dump(mode="json")` / `model_dump_json()` | модель → словник з Python-об'єктами / з JSON-типами / рядок JSON |
| `model_json_schema()` | опис моделі для інших програм — основа `/docs` у FastAPI |
| `TypeAdapter` | перевірка типів без моделі: `list[RawNews]` |
| `validate_news` + `Rejected` | перевірені окремо, відхилені з причинами — нічого не губиться мовчки |
| Межа довіри | дані ззовні — «сирі»; перевіряй один раз на вході, далі — лише моделі |

## Самоперевірка { #self-check }

1. Чим відрізняється перевірка `mypy` від перевірки Pydantic? Чи можна обійтися чимось одним?
2. Що дає `TypedDict` порівняно з `dict`?
3. Чому `published_time: time | None`, а не `time`?
4. Навіщо `model_validator(mode="before")` у `NewsItem`, а не `mode="after"`?
5. Чому `validate_news` повертає відхилені новини, а не просто пропускає їх?
6. Чим небезпечний розбір URL через `replace`/`split`?
7. Чому в `validate_news` — `except ValidationError`, а не просто `except Exception`?

??? success "Відповіді"

    1. `mypy` перевіряє **код** до запуску; Pydantic — **дані** під час роботи. Код може бути бездоганно типізований, а дані з інтернету — будь-якими, і навпаки — тож потрібні обидва.
    2. mypy знає ключі й типи значень: одруківка `"titel"` — помилка до запуску (`TypedDict "RawNews" has no key "titel"`), а не `KeyError` у роботі.
    3. У 31 новини зі знімка часу немає. `time | None` чесно це описує, і mypy змусить обробити `None`.
    4. `source`, `lang`, `category` не приходять з HTML — їх треба вивести з URL **до** перевірки полів, інакше модель не створиться без обов'язкових полів.
    5. Щоб нічого не губилося мовчки: відхилене можна порахувати, показати й виправити парсер.
    6. Він працює лише для точного збігу рядка: піддомен, `http://` замість `https://`, параметри запиту — і результат тихо стає неправильним. `urlsplit` розбирає URL за стандартом.
    7. `ValidationError` — очікувана подія: погані дані. Будь-який інший виняток — баг у нашому коді; `except Exception` сховав би його серед «відхилених новин».

## Що далі { #next }

[Крок 2. Перший API на FastAPI](../02_fastapi_basics/index.md) — `NewsItem` стає відповіддю API: `GET /api/news` з фільтрами, `POST /api/scrape`, `/docs` з тієї самої JSON Schema, а неправильні параметри запиту — `422` з тим самим форматом помилок, що й `ValidationError`.
