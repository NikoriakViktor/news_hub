# Режими lax і strict

## Проблема { #problem }

Клієнт надіслав `{"guests": "2"}`, а модель чекає `int`. Pydantic за замовчуванням не відмовляє, а перетворює: `"2"` → `2`. Для форм і query-параметрів це зручно, бо там усе — рядки. Для API платежів чи прапорця `is_admin` небажано, щоб `"yes"` ставало `True`. Режим `strict` вимикає перетворення, але в FastAPI він ламає й те, що мало працювати, — дати. Тут розберемося, що саме перетворює lax і де strict доречний.

## Ментальна модель { #mental-model }

| | lax (за замовчуванням) | strict |
|---|---|---|
| ідея | прийняти значення, якщо його **однозначно** можна перетворити | прийняти лише значення потрібного типу |
| `"5"` → `int` | `5` | помилка `int_type` |
| `5.5` → `int` | помилка `int_from_float` — дробову частину Pydantic 2 не відкидає | помилка |
| `123` → `str` | помилка `string_type` — число в рядок Pydantic 2 не перетворює | помилка |
| виняток | — | у **JSON** рядки дозволені для `date`, `datetime`, `UUID`, `Decimal` (у JSON немає таких типів). Але FastAPI цей виняток не використовує, див. [нижче](#fastapi) |

## Що перетворює lax { #lax }

[`examples/pydantic_v2/strict_demo.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/pydantic_v2/strict_demo.py):

```text
--- 1. lax: що Pydantic перетворює сам (validate_python)
   int       ← '5'                                        lax: 5                                  strict: ✗ int_type
   int       ← ' 5 '                                      lax: 5                                  strict: ✗ int_type
   int       ← 5.0                                        lax: 5                                  strict: ✗ int_type
   int       ← 5.5                                        lax: ✗ int_from_float                   strict: ✗ int_type
   int       ← True                                       lax: 1                                  strict: ✗ int_type
   int       ← '5.0'                                      lax: 5                                  strict: ✗ int_type
   float     ← '1.5'                                      lax: 1.5                                strict: ✗ float_type
   float     ← 3                                          lax: 3.0                                strict: 3.0
   str       ← 123                                        lax: ✗ string_type                      strict: ✗ string_type
   str       ← b'cheese'                                  lax: 'cheese'                           strict: ✗ string_type
   bool      ← 'true'                                     lax: True                               strict: ✗ bool_type
   bool      ← 'yes'                                      lax: True                               strict: ✗ bool_type
   bool      ← 'on'                                       lax: True                               strict: ✗ bool_type
   bool      ← '1'                                        lax: True                               strict: ✗ bool_type
   bool      ← 1                                          lax: True                               strict: ✗ bool_type
   bool      ← 2                                          lax: ✗ bool_parsing                     strict: ✗ bool_type
   bool      ← 'так'                                      lax: ✗ bool_parsing                     strict: ✗ bool_type
   date      ← '2026-12-01'                               lax: datetime.date(2026, 12, 1)         strict: ✗ date_type
   datetime  ← 1700000000                                 lax: datetime.datetime(2023, 11, 14, 22, 13, 20, tzinfo=TzInfo(0)) strict: ✗ datetime_type
   UUID      ← '6f1c0a2e-8f4b-4e7e-9a77-2a1f3c4d5e6f'     lax: UUID('6f1c0a2e-8f4b-4e7e-9a77-2a1f3c4d5e6f') strict: ✗ is_instance_of
   Decimal   ← 0.1                                        lax: Decimal('0.1')                     strict: ✗ is_instance_of
   list      ← ('1', 2)                                   lax: [1, 2]                             strict: ✗ list_type
```

Правило lax — **перетворювати лише без втрати інформації**:

- рядок з числом, навіть з пробілами чи `"5.0"`, стає `int`; `5.0` теж, а `5.5` — ні;
- `bool` приймає `true/false`, `yes/no`, `on/off`, `1/0` (рядки й числа), але не `2` і не `"так"`;
- рядок ISO 8601 — `date`/`datetime`; число — Unix-час у UTC;
- `int` → `float` дозволено навіть у strict: ціле число — коректний `float`;
- кортеж — список, елементи перетворюються кожен окремо.

Повна таблиця — [Conversion Table](https://docs.pydantic.dev/latest/concepts/conversion_table/) у документації Pydantic.

## Як увімкнути strict { #enable }

```python title="strict_demo.py (фрагмент)"
class Account(BaseModel):
    number: int = Field(strict=True)              # 1. поле
    pin: Annotated[int, Strict()]                 # 2. Annotated + Strict() (або StrictInt)
    balance: float                                # lax


class StrictAccount(BaseModel):
    model_config = ConfigDict(strict=True)        # 3. уся модель
    number: int
    balance: float = Field(strict=False)          # виняток для одного поля

StrictAccount.model_validate(data, strict=False)  # 4. параметр виклику
```

```text
--- 3. чотири способи увімкнути strict і що сильніше
   Account (Field strict + Strict())                    ✗ [('number', 'int_type'), ('pin', 'int_type')]
   StrictAccount (ConfigDict strict, balance lax)       ✗ [('number', 'int_type')]
   StrictAccount, number=42                             StrictAccount(number=42, balance=10.5)
   StrictAccount.model_validate(..., strict=False)      StrictAccount(number=42, balance=10.5)
   Account.model_validate(..., strict=False)            Account(number=42, pin=1234, balance=10.5)
   Account.model_validate(number=42, pin=1234, strict=True) ✗ [('balance', 'float_type')]
```

- `Field(strict=False)` на полі перекриває `strict=True` моделі: `balance` прийняв `"10.5"`.
- **Параметр виклику `strict=` перекриває все**, навіть `Field(strict=True)`: з `strict=False` поле `number` прийняло `"42"`. Тож `strict=False` у виклику вимикає захист, який автор моделі вважав обов'язковим.
- Готові типи: `StrictInt`, `StrictFloat`, `StrictStr`, `StrictBool`, `StrictBytes` — те саме, що `Annotated[int, Strict()]`.

## Strict у FastAPI { #fastapi }

```python title="strict_demo.py (фрагмент)"
class Booking(BaseModel):
    model_config = ConfigDict(strict=True)
    guests: int
    start: date
    vip: StrictBool = False


@app.get("/rooms")
def rooms(floor: Annotated[int, Query(strict=True)] = 1) -> dict[str, int]: ...
```

```text
--- 2. strict у Python і в JSON: рядок дати
   date     validate_python(strict) ✗ date_type            validate_json(strict) datetime.date(2026, 12, 1)
   UUID     validate_python(strict) ✗ is_instance_of       validate_json(strict) UUID('6f1c0a2e-8f4b-4e7e-9a77-2a1f3c4d5e6f')
   Decimal  validate_python(strict) ✗ is_instance_of       validate_json(strict) Decimal('0.10')
   int      validate_python(strict) ✗ int_type             validate_json(strict) ✗ int_type
--- 4. strict у FastAPI
   POST /bookings JSON-число і дата-рядок    → 422 [('start', 'date_type')]
   POST /bookings guests: "2"                → 422 [('guests', 'int_type'), ('start', 'date_type')]
   POST /bookings vip: 1                     → 422 [('start', 'date_type'), ('vip', 'bool_type')]
   GET /rooms?floor=3 (Query strict=True)   → 422 [('floor', 'int_type')]
```

**Strict на всю модель у FastAPI відхиляє правильний запит**: `{"guests": 2, "start": "2026-12-01"}` → `422 date_type`. `model_validate_json` у strict-режимі прийняв би рядок дати. Але FastAPI спершу розбирає JSON у словник, а потім перевіряє його як об'єкти Python (`validate_python` у `fastapi/_compat/v2.py`), і виняток для JSON не діє. Те саме з `UUID` і `Decimal`.

**`Query(strict=True)` для числа відхиляє кожен запит.** У адресі немає типів, `?floor=3` — завжди рядок `"3"`. Те саме з `Path`, `Header`, `Cookie` і формами.

Практичне правило для FastAPI: strict — **точково на полях тіла**, де перетворення небезпечне (`StrictBool` для прапорців, `StrictInt` для сум і кількостей), а не `ConfigDict(strict=True)` на всю модель і не на query/path.

## У News Hub { #news-hub }

Strict у News Hub немає, і lax там працює на користь:

- `published_time: time | None` приймає `"10:30"` з HTML і перетворює на `time` ([крок 1](../tutorials/01_typing_pydantic/index.md));
- query-параметр `limit` у `GET /api/news` і пошуку — рядок з адреси, які lax перетворює на `int`, а `Query(ge=..., le=...)` обмежує;
- відповідь LLM перевіряється `model_validate_json` ([крок 7](../tutorials/07_llm_api/index.md)): модель може повернути число рядком, і lax це виправить. Межі задають `Literal` і `Field`, а не strict.

## Типові помилки { #mistakes }

| Помилка | Наслідок | Як правильно |
|---|---|---|
| `ConfigDict(strict=True)` на модель тіла FastAPI з `date`/`UUID`/`Decimal` | правильні запити → `422` | strict точково: `StrictInt`, `StrictBool` |
| `strict=True` на `Query`/`Path`/`Header` | жоден запит не проходить | lax + обмеження `ge`/`le`/`Literal` |
| увімкнути strict на робочому публічному API | клієнти, що слали числа рядками, отримують `422` | нова версія API або поступово, з моніторингом `int_type` у журналах |
| чекати, що lax обріже `12.99` до `12` | `int_from_float` — і це правильно | якщо потрібні копійки — `Decimal`, а не `int`/`float` |
| чекати, що lax перетворить `123` на `"123"` | `string_type` | клієнт надсилає рядок, або `Field(coerce_numbers_to_str=True)` |
| `model_validate(data, strict=False)` «щоб пройшло» | вимикає й `Field(strict=True)` | виправити дані, а не режим |

## Безпека { #security }

- **Прапорці доступу — `StrictBool`.** У lax `"yes"`, `"on"`, `"1"` і `1` стають `True`. Якщо значення збирає інший сервіс або форма, легко отримати `True` там, де ніхто його не надсилав свідомо.
- **Гроші — `Decimal` з `max_digits`/`decimal_places`, не `float`.** Lax не втрачає дробову частину (`5.5` → помилка для `int`), але `float` сам по собі втрачає точність.
- **Strict не замінює обмежень.** `StrictInt` прийме `-1_000_000`; межі задають `ge`/`le`, `Literal`, `max_length`.

## Питання { #questions }

1. Що зробить lax з `"5"`, `5.5` і `123` для полів `int`, `int` і `str`?
2. Які рядки lax приймає як `True` для `bool`?
3. Чому `ConfigDict(strict=True)` у моделі тіла FastAPI відхиляє рядок дати, хоча документація Pydantic каже, що в JSON strict його приймає?
4. Чому `Query(strict=True)` для `int` не має сенсу?
5. Що сильніше: `Field(strict=True)` чи `model_validate(..., strict=False)`?
6. Де в API доречний `StrictBool`?

??? success "Відповіді"

    1. `5`; помилка `int_from_float`; помилка `string_type`.
    2. `"true"`, `"yes"`, `"on"`, `"1"` (і їхні варіанти в іншому регістрі); також число `1`.
    3. FastAPI розбирає JSON сам і перевіряє словник через `validate_python`, а виняток для дат діє лише у `validate_json`.
    4. Query-параметр завжди рядок, тож strict-`int` не пройде ніколи.
    5. Параметр виклику: `strict=False` у `model_validate` перекриває навіть `Field(strict=True)`.
    6. Для прапорців, від яких залежать права чи дії: `is_admin`, `confirm`, `notify`.

## Що далі { #next }

[Частина II. Типи і Pydantic](README.md) — решта розділів частини.

**Джерела:** Pydantic — [Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/), [Conversion Table](https://docs.pydantic.dev/latest/concepts/conversion_table/), [Standard Library Types — Booleans](https://docs.pydantic.dev/latest/api/standard_library_types/#booleans); FastAPI — [Query Parameters and String Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/).
