# news_hub — новинний агрегатор курсу

Сторінки rbc.ua → `parse_rbc_news` → `RawNews` → перевірка `NewsItem` (Pydantic) → PostgreSQL / SQLite
(SQLAlchemy 2 async) → кеш Redis → FastAPI → аналіз LLM (Gemini / Anthropic). Python 3.10+.

## Команди
- `pytest -m unit` — швидкі тести без бази, Redis і мережі; запускати після кожної зміни
- `pytest` — усі тести (SQLite у пам'яті + fakeredis + локальний aiohttp-сервер + FakeLLM)
- `pytest -m llm` — справжні виклики моделі; лише коли про це попросили (витрачає квоту)
- `mypy --strict news_hub` — типи; має бути чисто
- `alembic revision --autogenerate -m "…"` після зміни `tables.py`; міграцію перечитати очима

## Структура
- `news_hub/parser.py` — HTML rbc.ua → `list[RawNews]` (лише рядки, без перевірок)
- `news_hub/models.py` — `NewsItem`, `validate_news`, перевірка доменів
- `news_hub/scraper.py` — aiohttp; `repository.py` — увесь SQL; `api.py` — ендпоінти
- `news_hub/llm.py` — `LLMClient` і провайдери, `CircuitBreaker`; `analysis.py` — `NewsAnalysis`, промпт, `analyze_news`
- `tests/unit/`, `tests/integration/`, `tests/fixtures/` — збережені сторінки для тестів

## Правила
- Будь-яке джерело новин повертає `list[RawNews]`; перевіряє лише `NewsItem`. Відхилене — у `rejected`, не мовчки.
- Домени — лише точний збіг або піддомен (`host == d or host.endswith("." + d)`), ніколи `endswith(d)`.
- Тести не ходять у мережу: нова розмітка → файл у `tests/fixtures/` + тест конвеєра «парсер → модель».
- Не змінюй наявні тести, щоб вони пройшли. Якщо тест здається хибним — зупинись і поясни чому.
- Нових залежностей не додавай; якщо без неї ніяк — зупинись і поясни, навіщо вона.
- Секрети — лише зі змінних середовища; `.env` не читати й не комітити.
- Відповідь LLM — лише через `NewsAnalysis` (Pydantic); текст новини в промпті — між `<news>` і `</news>`, як дані.
- Тести не викликають справжню модель: `FakeLLM` (підміна `get_llm_client`); справжні виклики — лише `tests/live/`.
- Змінив промпт чи `NewsAnalysis` — збільш `PROMPT_VERSION` (інакше кеш віддаватиме старі відповіді).
- Анотації типів скрізь; `logging.getLogger("news_hub")` замість `print`; коментарі й docstring — українською.
