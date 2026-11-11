# Налаштування { #setup }

## 1. Клонуй репозиторій

```bash
git clone https://github.com/NikoriakViktor/news_hub.git
cd news_hub
```

## 2. Окреме середовище на крок { #venv }

Кожен крок має свій `requirements.txt` (з кроку 10 — ще й `requirements-dev.txt` для тестів і mypy).
Найпростіше — один venv у корені й перевстановлення залежностей при переході на новий крок:

=== "Linux / macOS"

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    cd steps/02_fastapi_basics
    pip install -r requirements.txt
    ```

=== "Windows"

    ```bat
    py -m venv .venv
    .venv\Scripts\activate
    cd steps\02_fastapi_basics
    pip install -r requirements.txt
    ```

Кроки 10–12: `pip install -r requirements-dev.txt` (він сам підтягує `requirements.txt`).

## 3. Перевір, що крок робочий { #check }

```bash
pytest -q
```

Тести не потребують ні PostgreSQL, ні Redis, ні мережі: база — SQLite у пам'яті, Redis — `fakeredis`,
LLM — `FakeLLM`, Telegram — двійник API. Скільки тестів очікувати — у README кроку і на сторінці кроку.

## 4. Запуск API { #run }

```bash
uvicorn news_hub.api:app --reload      # → http://127.0.0.1:8000/docs
```

| Кроки | Що потрібно для запуску |
|---|---|
| 1 | лише Python: крок без API |
| 2 | нічого: новини — у пам'яті процесу |
| 3 | нічого: без `DATABASE_URL` — файл SQLite `news_hub.db`; спершу `alembic upgrade head` |
| 4–9 | + Redis; без нього — `REDIS_URL=fakeredis://` |
| 10–12 | Docker; з кроку 11 — увесь стек через `docker compose up` (README кроку) |

## 5. PostgreSQL і Redis у Docker (за бажанням) { #services }

З кроку 3 у папці кроку є `docker-compose.yml`. Для кроків 3–9 він піднімає лише сервіси, а API ти запускаєш сам:

```bash
docker compose up -d db redis          # крок 3 — лише db
export DATABASE_URL=postgresql+asyncpg://news:news@localhost:5432/news_hub   # Windows: set DATABASE_URL=...
export REDIS_URL=redis://localhost:6379/0
alembic upgrade head
uvicorn news_hub.api:app --reload
```

Точні команди кожного кроку — у розділі «Запуск» на його сторінці.
