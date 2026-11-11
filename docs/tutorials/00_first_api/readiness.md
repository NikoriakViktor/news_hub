# Перевір себе перед кроком 1

## Навіщо { #why }

Книга не вчить Python, термінал і git з нуля: з кроку 1 код одразу справжній. Якщо якоїсь основи бракує, на кроці 3 чи 5 ти загубишся не в FastAPI, а в незнайомому `with` чи `git diff`. Перевір себе: спершу відповідай сам, потім розгортай відповідь.

Як рахувати: за кожною темою — чи відповів ти **без підказки**.

| Результат | Що робити |
|---|---|
| усе або майже все | переходь до [кроку 1](../01_typing_pydantic/index.md) |
| провал в одній-двох темах | підтягни саме їх за посиланнями в кінці теми — це кілька вечорів, а не новий курс |
| провал у Python | спершу Python: без нього решта книги не має сенсу |

## 1. Python { #python }

**1.1.** Що надрукує код?

```python
class Account:
    def __init__(self, balance):
        self.balance = balance

    def withdraw(self, amount):
        if amount > self.balance:
            raise ValueError("недостатньо коштів")
        self.balance -= amount


account = Account(100)
try:
    account.withdraw(150)
except ValueError as error:
    print("помилка:", error)
print(account.balance)
```

??? success "Відповідь"

    ```text
    помилка: недостатньо коштів
    100
    ```

    `raise` перериває метод до `self.balance -= amount`, тому баланс не змінився. Тут перевіряються класи, `self`, винятки і `try/except` — у News Hub вони на кожній сторінці.

**1.2.** Що надрукує код?

```python
news = [{"title": "A", "lang": "uk"}, {"title": "B", "lang": "en"}, {"title": "C", "lang": "uk"}]
print([item["title"] for item in news if item["lang"] == "uk"])
```

??? success "Відповідь"

    `['A', 'C']` — генератор списку з умовою над списком словників. Саме такі дані (список новин-словників) повертає парсер у кроці 1.

**1.3.** У проєкті є файл `news_hub/models.py` з класом `NewsItem`. Як імпортувати його в `news_hub/api.py`? Що має бути в папці `news_hub`, щоб імпорт `from news_hub.models import NewsItem` працював з кореня проєкту?

??? success "Відповідь"

    `from news_hub.models import NewsItem` (або відносно: `from .models import NewsItem`). `news_hub` — пакет: папка з `__init__.py`, а запуск — з папки, де лежить `news_hub/` (тоді Python її бачить).

**1.4.** Що робить `with open("data.json", encoding="utf-8") as file:` і чим це краще за `file = open(...)`?

??? success "Відповідь"

    Відкриває файл і **гарантовано закриває** його після блоку — навіть якщо всередині стався виняток. У книзі `with` — це ще й сесії бази, HTTP-клієнти й тимчасові папки в тестах.

**Підтягнути:** [Підручник з Python](https://docs.python.org/uk/3/tutorial/) (офіційний, українською) — розділи 4–9: керування потоком, структури даних, модулі, введення-виведення, помилки й винятки, класи.

## 2. Термінал, venv і pip { #terminal }

**2.1.** Ти в папці `steps/02_fastapi_basics`. Як створити віртуальне середовище, увімкнути його і встановити залежності з `requirements.txt`?

??? success "Відповідь"

    ```bash
    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

    Кожен крок — окреме середовище, бо в різних кроках різні залежності ([Налаштування](../../00_getting_started/local_setup.md#venv)).

**2.2.** Що робить `export DATABASE_URL=sqlite:///news.db` (Windows: `set DATABASE_URL=...`) і чи побачить це значення програма, запущена в **іншому** вікні терміналу?

??? success "Відповідь"

    Створює змінну середовища для цього вікна терміналу і всіх програм, запущених з нього. В іншому вікні — ні. Так у News Hub передаються адреса бази, ключі й паролі — не через код.

**2.3.** Сервер запущено (`uvicorn ...`), термінал «завис». Як його зупинити і як, не зупиняючи, виконати `curl`?

??? success "Відповідь"

    `Ctrl+C` зупиняє. Для `curl` — друге вікно (вкладка) терміналу: сервер займає перше, поки працює.

**Підтягнути:** розділ [Налаштування](../../00_getting_started/local_setup.md) цієї книги; про venv — [Підручник з Python, розділ 12](https://docs.python.org/uk/3/tutorial/venv.html).

## 3. Git { #git }

**3.1.** Чим відрізняються `git status`, `git diff` і `git log --oneline`?

??? success "Відповідь"

    `status` — які файли змінено і що підготовлено до коміту; `diff` — самі зміни рядок за рядком; `log --oneline` — історія комітів, по рядку на коміт.

**3.2.** У книзі кожен крок — окрема папка. Що покаже команда нижче?

```bash
git diff --no-index --stat steps/01_typing_pydantic steps/02_fastapi_basics
```

??? success "Відповідь"

    Які файли відрізняються між двома **папками** і на скільки рядків (`--stat`). `--no-index` дозволяє порівнювати будь-які дві папки, а не лише версії в історії git. Так у кожному кроці видно, що саме додалось ([Як читати кроки](../../00_getting_started/how_to_use.md#compare)).

**Підтягнути:** [Pro Git](https://git-scm.com/book/uk/v2) (українською) — розділи 1–3.

## 4. HTTP і JSON { #http }

**4.1.** Який метод HTTP для кожної дії: отримати список новин; додати новину; видалити новину номер 5?

??? success "Відповідь"

    `GET /news`; `POST /news` (новина — у тілі запиту); `DELETE /news/5`.

**4.2.** Клієнт отримав `404`, `422` і `500`. Хто в кожному випадку має щось виправити?

??? success "Відповідь"

    `404` — клієнт (такої адреси чи запису немає); `422` — клієнт (дані не пройшли перевірку); `500` — сервер (помилка в його коді). Якщо [Крок 0](first_app.md#error-422) пройдено, ти це вже бачив наживо.

**4.3.** Чи правильний це JSON: `{'id': 7}`? Що поверне `json.loads('{"id": 7, "tags": ["uk", "sport"]}')["tags"][1]`?

??? success "Відповідь"

    Ні: у JSON ключі й рядки — лише в **подвійних** лапках. `json.loads("{'id': 7}")` дає `JSONDecodeError: Expecting property name enclosed in double quotes`. Другий вираз поверне `'sport'`: JSON-об'єкт став словником Python, список — списком.

**Підтягнути:** [Частина I. HTTP і REST](../../01_http_and_rest/README.md) цієї книги; [MDN: огляд HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview) (англійською).

## 5. SQL (знадобиться з кроку 3) { #sql }

**5.1.** Таблиця `news` має колонки `id`, `url`, `lang`. Напиши запит: `id` і `url` усіх новин українською.

??? success "Відповідь"

    ```sql
    SELECT id, url FROM news WHERE lang = 'uk';
    ```

**5.2.** Колонка `url` оголошена `UNIQUE`. Що станеться, якщо вдруге вставити новину з тим самим `url`?

??? success "Відповідь"

    База відмовить: `IntegrityError: UNIQUE constraint failed: news.url` (так у SQLite). У кроці 3 News Hub ловить саме цю помилку й відповідає клієнту `409 Conflict` — «така новина вже є».

**Підтягнути:** [SQLBolt](https://sqlbolt.com/) (англійською, інтерактивно) — уроки 1–6 і 13.

## Не обов'язково зараз { #later }

Цього можна не знати: книга пояснить, коли дійде.

- `async` / `await` — [Частина IV](../../04_async/README.md) і крок 2;
- Docker — з кроку 10;
- Django — якщо знаєш, сторінки з порівнянням допоможуть, але FastAPI вивчається з нуля.

## Що далі { #next }

[Крок 1. Типи і Pydantic](../01_typing_pydantic/index.md).
