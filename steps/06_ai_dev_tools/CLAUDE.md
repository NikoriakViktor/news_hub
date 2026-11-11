# news_hub — новинний агрегатор курсу

Сторінки rbc.ua → `parse_rbc_news` → `RawNews` → перевірка `NewsItem` (Pydantic) → PostgreSQL / SQLite
(SQLAlchemy 2 async) → кеш Redis → FastAPI. Python 3.10+.

## Команди
- `pytest -m unit` — швидкі тести без бази, Redis і мережі; запускати після кожної зміни
- `pytest` — усі тести (SQLite у пам'яті + fakeredis + локальний aiohttp-сервер)
- `mypy --strict news_hub` — типи; має бути чисто
- `alembic revision --autogenerate -m "…"` після зміни `tables.py`; міграцію перечитати очима

## Структура
- `news_hub/parser.py` — HTML rbc.ua → `list[RawNews]` (лише рядки, без перевірок)
- `news_hub/models.py` — `NewsItem`, `validate_news`, перевірка доменів
- `news_hub/scraper.py` — aiohttp; `repository.py` — увесь SQL; `api.py` — ендпоінти
- `tests/unit/`, `tests/integration/`, `tests/fixtures/` — збережені сторінки для тестів

## Правила
- Будь-яке джерело новин повертає `list[RawNews]`; перевіряє лише `NewsItem`. Відхилене — у `rejected`, не мовчки.
- Домени — лише точний збіг або піддомен (`host == d or host.endswith("." + d)`), ніколи `endswith(d)`.
- Тести не ходять у мережу: нова розмітка → файл у `tests/fixtures/` + тест конвеєра «парсер → модель».
- Не змінюй наявні тести, щоб вони пройшли. Якщо тест здається хибним — зупинись і поясни чому.
- Нових залежностей не додавай; якщо без неї ніяк — зупинись і поясни, навіщо вона.
- Секрети — лише зі змінних середовища; `.env` не читати й не комітити.
- Анотації типів скрізь; `logging.getLogger("news_hub")` замість `print`; коментарі й docstring — українською.
