# Engine, сесії й таблиця

> Крок 3 · розділ 1 з 5. Код: [`news_hub/db.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/news_hub/db.py), [`news_hub/tables.py`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/03_sqlalchemy_alembic/news_hub/tables.py).
> Теорія: [Частина V. Бази даних](../../05_databases/README.md).

## Задача { #task }

Підключити агрегатор до бази даних так, щоб:

- той самий код працював і з PostgreSQL (сервер), і з SQLite (свій комп'ютер без Docker, тести);
- адреса бази не була зашита в код;
- таблиця новин описувалась так само, як ми вже описуємо дані, — анотаціями типів.

## Зміна 1: `db.py` — підключення { #db }

```python title="news_hub/db.py (фрагмент)"
# postgresql+asyncpg://news:news@localhost:5432/news_hub  — PostgreSQL (docker compose up -d db)
# sqlite+aiosqlite:///news_hub.db                          — файл поруч із проєктом
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///news_hub.db")


def make_engine(url: str = DATABASE_URL, echo: bool = False, **options: Any) -> AsyncEngine:
    if url.startswith("postgresql"):
        return create_async_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True, echo=echo, **options)
    sqlite_engine = create_async_engine(url, echo=echo, **options)
    event.listen(sqlite_engine.sync_engine, "connect", _unicode_lower)
    return sqlite_engine


engine = make_engine()

# expire_on_commit=False — після commit() поля об'єкта доступні без нового SELECT
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    """Базовий клас моделей; Base.metadata — реєстр таблиць для Alembic і тестів."""
```

Чотири об'єкти, і кожен має одну роботу:

| Об'єкт | Що це | Скільки їх |
|---|---|---|
| `DATABASE_URL` | адреса бази одним рядком | одна на процес; зі змінної середовища |
| `engine` | **пул з'єднань** з базою | один на процес, створюється при імпорті |
| `SessionFactory` | фабрика сесій | одна |
| сесія (`AsyncSession`) | **робоче місце одного запиту**: накопичує зміни, `commit()` відправляє їх однією транзакцією | одна на HTTP-запит ([розділ 3](session_per_request.md)) |

### Адреса бази { #url }

`postgresql+asyncpg://news:news@localhost:5432/news_hub` читається зліва направо:

| Частина | Значення |
|---|---|
| `postgresql` | **діалект** — яку мову SQL генерувати |
| `+asyncpg` | **драйвер** — бібліотека, що говорить з базою; `asyncpg` і `aiosqlite` асинхронні, тому їх можна чекати через `await` |
| `news:news` | користувач і пароль |
| `localhost:5432` | хост і порт |
| `/news_hub` | назва бази |

Для SQLite — `sqlite+aiosqlite:///news_hub.db`: три скісні риски й шлях до файлу. Без шляху (`sqlite+aiosqlite://`) база живе в пам'яті, так працюють тести.

Адреса береться зі змінної середовища, тож код однаковий на твоєму комп'ютері, у тестах і на сервері. Без `DATABASE_URL` — файл SQLite, і крок працює без PostgreSQL.

### Пул з'єднань { #pool }

Відкрити з'єднання з PostgreSQL — це мережеве рукостискання й автентифікація. Робити це на кожен запит дорого, тому `engine` тримає **пул**:

- `pool_size=10` — до 10 з'єднань лишаються відкритими й чекають наступних запитів;
- `max_overflow=20` — на піку ще до 20 тимчасових;
- `pool_pre_ping=True` — перед видачею з'єднання перевіряє, що воно живе (PostgreSQL могли перезапустити).

У SQLite своя модель з'єднань (це файл, а не сервер), тому ці налаштування — лише для PostgreSQL.

### SQLite і кирилиця { #unicode-lower }

Друга гілка `make_engine` підміняє в SQLite функцію `lower()`. Причина — у вбудованому `lower()` SQLite знає лише латиницю:

```python
import sqlite3

print(sqlite3.connect(":memory:").execute("select lower('ЗЕЛЕНСЬК'), lower('ABC')").fetchone())
```

```text
('ЗЕЛЕНСЬК', 'abc')
```

Без підміни пошук без урахування регістру (`/api/news/search?q=ЗЕЛЕНСЬК`, [розділ 4](crud.md#search)) на SQLite не знаходив би нічого. `_unicode_lower` реєструє на кожне нове з'єднання Python-версію `lower`:

```python title="news_hub/db.py (фрагмент)"
def _unicode_lower(dbapi_connection: Any, _record: Any) -> None:
    dbapi_connection.create_function("lower", 1, lambda text: text.lower() if isinstance(text, str) else text,
                                     deterministic=True)
```

PostgreSQL цього не потребує: там `ILIKE` і `lower()` знають Unicode.

## Зміна 2: `tables.py` — таблиця як клас { #table }

```python title="news_hub/tables.py"
class NewsRow(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)    # унікальність гарантує база, а не код
    title: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(100), index=True)
    lang: Mapped[str] = mapped_column(String(2), index=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    published_time: Mapped[time | None] = mapped_column(Time)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

| Запис | Що дає в таблиці |
|---|---|
| `Mapped[str]` | стовпець `NOT NULL` |
| `Mapped[time \| None]` | `NULL` дозволено |
| `primary_key=True` | `id` — первинний ключ, номер дає база |
| `unique=True` | обмеження `UNIQUE (url)` |
| `index=True` | індекс: фільтри `?lang=`, `?source=`, `?category=` не перебирають усю таблицю |
| `server_default=func.now()` | час збору ставить **база** в момент `INSERT` |

Ті самі анотації типів, що з кроку 1 описують дані для mypy і Pydantic, тепер описують і таблицю. Подивимось, який SQL з цього виходить (з папки кроку):

```python
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from news_hub.tables import NewsRow

print(CreateTable(NewsRow.__table__).compile(dialect=postgresql.dialect()))
for index in sorted(NewsRow.__table__.indexes, key=lambda i: i.name):
    print(CreateIndex(index).compile(dialect=postgresql.dialect()))
```

```text
CREATE TABLE news (
	id SERIAL NOT NULL,
	url VARCHAR(500) NOT NULL,
	title VARCHAR(300) NOT NULL,
	source VARCHAR(100) NOT NULL,
	lang VARCHAR(2) NOT NULL,
	category VARCHAR(100) NOT NULL,
	published_time TIME WITHOUT TIME ZONE,
	scraped_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (url)
)


CREATE INDEX ix_news_category ON news (category)
CREATE INDEX ix_news_lang ON news (lang)
CREATE INDEX ix_news_source ON news (source)
```

Те саме з `dialect=sqlite.dialect()` — інший SQL з тієї самої моделі:

```text
CREATE TABLE news (
	id INTEGER NOT NULL,
	...
	published_time TIME,
	scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (url)
)
```

`func.now()` — не текст функції, а «поточний час» узагалі: SQLAlchemy підставляє `now()` для PostgreSQL і `CURRENT_TIMESTAMP` для SQLite. До цього повернемося в [міграціях](alembic.md#autogenerate).

## Результат: дві моделі однієї новини { #two-models }

Тепер у проєкті дві моделі новини. Це навмисно:

| | `NewsItem` (Pydantic, `models.py`) | `NewsRow` (SQLAlchemy, `tables.py`) |
|---|---|---|
| Навіщо | **перевірити** дані з парсера чи тіла запиту | **зберегти** рядок таблиці |
| Звідки поля | з HTML і URL | з бази: `id`, `scraped_at` дає база |
| Правила | довжина заголовка, домен rbc.ua, `Literal["uk", "ru"]` | типи стовпців, `UNIQUE`, `NOT NULL`, індекси |
| Коли працює | до запису | під час запису й читання |

Відповідь API з'єднує обидві:

```python title="news_hub/api.py (фрагмент)"
class NewsOut(NewsItem):
    """NewsItem + те, що дає база. from_attributes — будується з об'єкта NewsRow."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    scraped_at: datetime
```

`from_attributes=True` дозволяє Pydantic читати поля з **атрибутів** об'єкта (`row.title`, `row.id`), а не лише зі словника. Тому ендпоінт повертає `NewsRow`, а `response_model=list[NewsOut]` перетворює його на JSON і заодно перевіряє, що в базі лежить правильна новина. Одна новина у відповіді `GET /api/news?limit=1` на PostgreSQL:

```text
{'title': 'Реформа ЗСУ', 'url': 'https://www.rbc.ua/rus/news/reforma-zsu-kih-zmin-armiyi-chekati-vzhe-1777644218.html', 'source': 'rbc.ua', 'lang': 'ru', 'category': 'Новини', 'published_time': None, 'id': 1, 'scraped_at': '2026-11-11T21:08:28.009909Z'}
```

На SQLite той самий запит дає `'scraped_at': '2026-11-11T21:10:57'` — без часового поясу й мікросекунд: SQLite зберігає `CURRENT_TIMESTAMP` як рядок UTC без зони. Ще одна причина ганяти тести й на PostgreSQL.

!!! note "Чому не одна модель на все"
    Змішати їх — значить або тягнути SQL у перевірку даних з парсера, або правила перевірки (домен rbc.ua, довжина заголовка) у таблицю. У них різні задачі й різний час роботи. Пізніше, у [кроці 7](../07_llm_api/index.md), таблиця отримає нові стовпці, а `NewsItem` для парсера лишиться тією самою.

## Правило { #rule }

!!! tip "Правило"
    Адреса бази — зі змінної середовища, engine — один на процес, сесія — одна на запит. Таблицю описуй класом з `Mapped[...]`, а дані ззовні перевіряй окремою Pydantic-моделлю: таблиця зберігає, модель перевіряє.

**Далі:** [Репозиторій замість `NewsStore`](repository.md) — хто пише SQL.
