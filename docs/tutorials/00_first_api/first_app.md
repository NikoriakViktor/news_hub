# Перший API на 13 рядків

## Задача { #task }

Запустити власний сервер, отримати від нього JSON у браузері, побачити документацію, яку ніхто не писав, і отримати першу помилку `422`.

## Зміна: файл `main.py` { #change }

[`examples/first_api/main.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/first_api/main.py):

```python title="main.py"
from fastapi import FastAPI

app = FastAPI(title="Перший API")


@app.get("/")
def hello() -> dict[str, str]:
    return {"message": "Привіт! Це відповідь сервера"}


@app.get("/news/{news_id}")
def get_news(news_id: int, lang: str = "uk") -> dict[str, int | str]:
    return {"id": news_id, "lang": lang, "title": f"Новина номер {news_id}"}
```

Рядок за рядком:

| Код | Що означає |
|---|---|
| `app = FastAPI(...)` | застосунок — те, що запускатиме сервер |
| `@app.get("/")` | «коли прийде `GET` на адресу `/`, виклич функцію нижче» |
| `return {...}` | звичайний словник Python; FastAPI сам перетворить його на JSON |
| `"/news/{news_id}"` | `{news_id}` — змінна частина адреси: `/news/7`, `/news/42` |
| `news_id: int` | **анотація типу** — FastAPI перевірить, що в адресі число, і передасть уже `int`, а не рядок |
| `lang: str = "uk"` | параметра немає в адресі → FastAPI шукає його після `?`: `/news/7?lang=en`; не передали — буде `"uk"` |

Анотації типів (`: int`, `-> dict[...]`) Python сам не перевіряє, а FastAPI — перевіряє. Про це весь [крок 1](../01_typing_pydantic/index.md).

## Запуск { #run }

З папки `examples/first_api`:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # fastapi і uvicorn
uvicorn main:app --reload
```

`main:app` — «з файлу `main.py` візьми змінну `app`». `--reload` — перезапускати сервер, коли змінюєш файл. Сервер пише:

```text
INFO:     Started server process [73905]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Номер процесу (`[73905]`) у тебе буде інший. Термінал «завис» — це нормально: сервер працює й чекає запитів. Зупинити — `Ctrl+C`.

## Результат: запити з браузера { #result }

Відкрий у браузері адреси по черзі. Браузер — теж клієнт: він надсилає `GET`. Нижче — що відповідає сервер (код і тіло):

| Адреса | Код | Тіло відповіді |
|---|---|---|
| http://127.0.0.1:8000/ | `200 OK` | `{"message":"Привіт! Це відповідь сервера"}` |
| http://127.0.0.1:8000/news/7 | `200 OK` | `{"id":7,"lang":"uk","title":"Новина номер 7"}` |
| http://127.0.0.1:8000/news/7?lang=en | `200 OK` | `{"id":7,"lang":"en","title":"Новина номер 7"}` |
| http://127.0.0.1:8000/nothing | `404 Not Found` | `{"detail":"Not Found"}` |

А в терміналі сервера з'являється рядок на кожен запит — так видно, що запит дійшов (`127.0.0.1:42330` — адреса й порт клієнта, у тебе числа будуть інші):

```text
INFO:     127.0.0.1:42330 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:42338 - "GET /news/7 HTTP/1.1" 200 OK
INFO:     127.0.0.1:42340 - "GET /news/7?lang=en HTTP/1.1" 200 OK
INFO:     127.0.0.1:42354 - "GET /nothing HTTP/1.1" 404 Not Found
```

Те саме без браузера, з терміналу (другого — перший зайнятий сервером):

```bash
curl -i http://127.0.0.1:8000/news/7
```

```text
HTTP/1.1 200 OK
date: Wed, 11 Nov 2026 21:10:46 GMT
server: uvicorn
content-length: 56
content-type: application/json

{"id":7,"lang":"uk","title":"Новина номер 7"}
```

`-i` показує **заголовки** відповіді — службові рядки перед тілом. `content-type: application/json` — сервер повідомляє клієнту: «у тілі JSON»; `content-length: 56` — розмір тіла в байтах (кирилиця займає по 2 байти на літеру).

## Перша помилка: `422` { #error-422 }

Відкрий http://127.0.0.1:8000/news/abc:

```text
HTTP/1.1 422 Unprocessable Entity

{"detail":[{"type":"int_parsing","loc":["path","news_id"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"abc"}]}
```

Функція `get_news` **навіть не викликалась**. FastAPI прочитав `news_id: int`, спробував перетворити `"abc"` на число, не зміг і сам відповів клієнту, що не так:

| Поле | Значення | Простими словами |
|---|---|---|
| `type` | `int_parsing` | не вдалося прочитати ціле число |
| `loc` | `["path", "news_id"]` | де: в адресі (`path`), частина `news_id` |
| `msg` | `Input should be a valid integer…` | пояснення для людини |
| `input` | `"abc"` | що прийшло насправді |

Без FastAPI цю перевірку довелося б писати самому в кожній функції. Забув — і `int("abc")` усередині функції дасть `500`: «сервер зламався», хоча винен клієнт. Детально формат таких помилок — [`ValidationError`](../../02_typing_and_pydantic/validation_error.md).

## `/docs`: документація, яку ніхто не писав { #docs }

Відкрий http://127.0.0.1:8000/docs. Там список адрес API з параметрами й типами, які FastAPI прочитав з коду. Натисни `GET /news/{news_id}` → **Try it out** → введи `7` → **Execute**. Сторінка сама надішле запит і покаже відповідь. Введи `abc` — побачиш той самий `422`.

Під капотом `/docs` читає опис API в машинному форматі OpenAPI — http://127.0.0.1:8000/openapi.json:

```text
{"openapi":"3.1.0","info":{"title":"Перший API","version":"0.1.0"},"paths":{"/":{"get":{"summary":"Hello", ...
```

`title` — це `FastAPI(title="Перший API")`, а `summary` FastAPI зробив з назви функції `hello`. Змінив код — змінилась і документація.

## Спробуй сам { #try }

1. Додай адресу `GET /about`, яка повертає `{"project": "News Hub", "step": 0}`. Збережи файл — `--reload` перезапустить сервер — і знайди нову адресу в `/docs`.
2. Зроби `lang` обов'язковим: прибери `= "uk"`. Що тепер відповідає `/news/7` без `?lang=`?
3. Зміни `news_id: int` на `news_id: str`. Що тепер відповідає `/news/abc`? Чому це гірше?

??? success "Відповіді"

    1. `@app.get("/about")` + функція, що повертає словник. Адреса з'являється в `/docs` без жодних інших змін.
    2. `422` з `"type": "missing"` і `"loc": ["query", "lang"]` — обов'язковий параметр не передали.
    3. `200` і `"id": "abc"`. Перевірка зникла: API обіцяє «новину номер abc», а клієнт не дізнається, що помилився.

## Правило { #rule }

!!! tip "Правило"
    Клієнт просить — сервер відповідає кодом і JSON. У FastAPI адреса — це декоратор, обробник — звичайна функція, а **анотації типів — це перевірка вхідних даних**: неправильний запит отримує `422` ще до твого коду, а `/docs` описує API саме з цих анотацій.

## Що далі { #next }

[Перевір себе перед кроком 1](readiness.md) — що треба знати, щоб далі не загубитися.
