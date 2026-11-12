# Шпаргалка Pydantic

Pydantic 2.13 і pydantic-settings 2.16. Фрагменти — з
[`examples/reference/cheatsheet_check.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/reference/cheatsheet_check.py),
вивід — його. Пояснення — [Частина II. Типи і Pydantic](../02_typing_and_pydantic/README.md).

## Модель цілком { #model }

```python
def strip_title(value: str) -> str:
    return " ".join(value.split())


Title = Annotated[str, AfterValidator(strip_title), Field(min_length=10)]


class News(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Title
    url: str = Field(pattern=r"^https://")
    tags: list[str] = []
    views: int = Field(0, ge=0)
    lang: Literal["uk", "ru"] = Field("uk", validation_alias="language")

    @field_validator("tags")
    @classmethod
    def lower_tags(cls, tags: list[str]) -> list[str]:
        return [tag.lower() for tag in tags]

    @model_validator(mode="after")
    def no_views_for_ru(self) -> "News":
        if self.lang == "ru" and self.views > 0:
            raise ValueError("лічильник лише для uk")
        return self

    @computed_field
    @property
    def domain(self) -> str:
        return self.url.split("/")[2]

    @field_serializer("tags")
    def tags_as_string(self, tags: list[str]) -> str:
        return ",".join(tags)
```

```text
model_dump()            → {'title': 'Новина про ШІ', 'url': 'https://rbc.ua/news/1', 'tags': 'ai,tech', 'views': 0, 'lang': 'uk', 'domain': 'rbc.ua'}
model_dump_json()       → {"title":"Новина про ШІ","url":"https://rbc.ua/news/1","tags":"ai,tech","views":0,"lang":"uk","domain":"rbc.ua"}
exclude/include         → {'title': 'Новина про ШІ', 'lang': 'uk'}
extra=forbid            → [('extra_forbidden', ('admin',))]
pattern + ge            → [('string_pattern_mismatch', ('url',)), ('greater_than_equal', ('views',))]
model_validator         → [('value_error', ())]
JSON Schema (поля)      → ['language', 'tags', 'title', 'url', 'views']
```

- Вхід `"  Новина   про   ШІ  "` → `"Новина про ШІ"`: спершу `str_strip_whitespace`, потім `AfterValidator`.
- Помилка `model_validator` має порожній `loc` — вона про модель, а не про поле (у FastAPI — `["body"]`).
- Схема входу (`model_json_schema()`) знає `language`, а не `lang`, і не знає `domain`: `computed_field` є лише у
  виході.

## `Field` { #field }

| Обмеження | Для | Код помилки |
|---|---|---|
| `min_length`, `max_length` | `str`, `list` | `string_too_short`, `string_too_long`, `too_short`, `too_long` |
| `ge`, `gt`, `le`, `lt` | числа | `greater_than_equal`, `less_than_equal`, … |
| `pattern=r"…"` | `str` | `string_pattern_mismatch` |
| `default=…`, `default_factory=list` | будь-що | — |
| `alias`, `validation_alias`, `serialization_alias` | ім'я поля ззовні | — |
| `description=`, `examples=[…]` | схема й `/docs` | — |
| `strict=True` | одне поле без перетворень | `int_type`, `string_type`, … |
| `exclude=True` | поле не йде в `model_dump` | — |

Докладно — [Моделі Pydantic 2](../02_typing_and_pydantic/pydantic_models.md#field).

## Валідатори { #validators }

| Що | Коли виконується | Для чого |
|---|---|---|
| `@field_validator("x")` (`mode="after"`) | після перевірки типу | правило одного поля; **повертай значення** |
| `@field_validator("x", mode="before")` | до перевірки типу, сире значення | нормалізація: `isinstance` першим рядком |
| `@model_validator(mode="after")` | після всіх полів, `self` готовий | правила між полями |
| `@model_validator(mode="before")` | до всього, сирий словник | інший формат входу |
| `Annotated[str, AfterValidator(fn)]` | як `field_validator`, але частина типу | одне правило на багато моделей |
| `@computed_field` + `@property` | при серіалізації | поле, обчислене з інших |

Помилка — `raise ValueError("…")` (не `assert`: зникає з `python -O`). Докладно —
[Валідатори і `computed_field`](../02_typing_and_pydantic/validators.md).

## `ConfigDict` { #config }

| Параметр | Що робить | Докладно |
|---|---|---|
| `extra="forbid"` / `"ignore"` (за замовчуванням) / `"allow"` | зайві поля: помилка / відкинути / зберегти | [`extra`](../02_typing_and_pydantic/config_dict.md#extra) |
| `frozen=True` | заборонити присвоєння, модель стає хешованою | [`frozen`](../02_typing_and_pydantic/config_dict.md#frozen) |
| `validate_assignment=True` | перевіряти присвоєння | [присвоєння](../02_typing_and_pydantic/config_dict.md#validate-assignment) |
| `from_attributes=True` | будувати з об'єкта (рядок SQLAlchemy) | [`from_attributes`](../02_typing_and_pydantic/config_dict.md#from-attributes) |
| `strict=True` | без перетворень типів для всієї моделі | [lax і strict](../02_typing_and_pydantic/strict_mode.md) |
| `str_strip_whitespace=True` | обрізати пробіли в усіх `str` | — |
| `populate_by_name=True` | приймати і alias, і ім'я поля | — |

`class Config: orm_mode = True` — синтаксис Pydantic 1; у Pydantic 2 — `model_config = ConfigDict(from_attributes=True)`.

## Серіалізація { #serialization }

| Що | Як |
|---|---|
| у `dict` з Python-об'єктами | `m.model_dump()` |
| у `dict`, придатний для JSON (`datetime` → рядок, `HttpUrl` → рядок) | `m.model_dump(mode="json")` |
| у JSON-рядок | `m.model_dump_json()` |
| лише передані поля (`PATCH`) | `m.model_dump(exclude_unset=True)` |
| частина полів | `include={…}`, `exclude={…}` |
| за alias | `by_alias=True` |
| своє перетворення поля | `@field_serializer("tags")` |
| з об'єкта / з JSON | `Model.model_validate(obj)`, `Model.model_validate_json(raw)` |
| тип без моделі | `TypeAdapter(list[int]).validate_python([...])` |

```python
class RowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str


class Patch(BaseModel):
    title: str | None = None
    views: int | None = None
```

```text
from_attributes         → id=1 title='Заголовок з бази даних'
PATCH exclude_unset     → {'title': 'Новий'}
TypeAdapter(list[int])  → [1, 2]
```

`PATCH` у News Hub — `NewsPatch` з валідатором, що забороняє явний `null`
([Моделі, `exclude_unset`](../02_typing_and_pydantic/pydantic_models.md#exclude-unset)).

## Типи { #types }

| Тип | Що приймає | Пастка | Докладно |
|---|---|---|---|
| <code>X &#124; None = None</code> | необов'язкове | без `= None` — обов'язкове | [анотації](../02_typing_and_pydantic/type_hints.md) |
| `Literal["uk", "ru"]` | лише ці значення | — | [анотації](../02_typing_and_pydantic/type_hints.md) |
| `Annotated[T, Field(…)]` | тип + обмеження | у звичайній функції без `@validate_call` нічого не перевіряє | [`Annotated`](../02_typing_and_pydantic/type_hints.md#annotated) |
| `HttpUrl` | `http`/`https` URL | не `str`: `str(url)` для бази й порівнянь; не захищає від SSRF | [`HttpUrl`](../02_typing_and_pydantic/special_types.md#url) |
| `EmailStr` | email | потрібен `email-validator` | [`EmailStr`](../02_typing_and_pydantic/special_types.md#email) |
| `AwareDatetime` | час з поясом | naive з SQLite у відповіді → `500` | [дати](../02_typing_and_pydantic/special_types.md#datetime) |
| `SecretStr` | секрет | `str()` дає `**********`; значення — `get_secret_value()` | [`SecretStr`](../02_typing_and_pydantic/settings.md#secret) |
| `StrictInt`, `StrictBool` | без перетворень | — | [strict](../02_typing_and_pydantic/strict_mode.md) |
| `TypedDict` | словник з ключами | на Python < 3.12 — з `typing_extensions` | [крок 1](../tutorials/01_typing_pydantic/type_hints_typeddict.md) |

## Налаштування { #settings }

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWS_", extra="ignore")
    database_url: str = "sqlite+aiosqlite:///news_hub.db"
    jwt_secret: SecretStr
```

```text
database_url            → sqlite+aiosqlite:///news_hub.db
jwt_secret              → ********** | get_secret_value: 32 символи
```

| Що | Як |
|---|---|
| встановити | `pip install pydantic-settings`; `from pydantic_settings import BaseSettings` (не з `pydantic`) |
| префікс змінних | `env_prefix="NEWS_"` → `NEWS_JWT_SECRET` |
| файл `.env` | `env_file=Path(__file__).parent / ".env"` — шлях від файлу, а не від папки запуску |
| чужі ключі в `.env` | `extra="ignore"`; за замовчуванням — `extra_forbidden` при старті |
| один екземпляр | `@lru_cache` навколо `Settings()` |

News Hub читає змінні через `os.getenv` і функції `load_*_settings()` — список і значення за замовчуванням у
[Змінних середовища](env_vars.md). Підхід з `BaseSettings` — [Налаштування](../02_typing_and_pydantic/settings.md).

## Помилки { #errors }

| Що | Як |
|---|---|
| усі помилки | `except ValidationError as error: error.errors()` → `type`, `loc`, `msg`, `input`, `ctx` |
| без даних користувача | `error.errors(include_input=False, include_context=False, include_url=False)` |
| у FastAPI | помилка запиту → `RequestValidationError` → `422`; помилка відповіді → `ResponseValidationError` → `500` |
| перевірка в тестах | за `type` і `loc`, не за текстом `msg` |

Докладно — [`ValidationError`](../02_typing_and_pydantic/validation_error.md).

## Що далі { #next }

- [Шпаргалка FastAPI](fastapi_cheatsheet.md) — де ці моделі стають параметрами й відповідями.
- [Міграція з Pydantic 1](../02_typing_and_pydantic/pydantic_models.md#migration).
