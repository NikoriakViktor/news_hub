# Zero to Hero — маршрут

12 кроків від парсера до production. Кожен крок — папка `steps/NN_*` з повним робочим проєктом;
сторінка кроку пояснює, що змінилося порівняно з попереднім і чому.

```mermaid
flowchart TD
    classDef step     fill:#eceff1,stroke:#546e7a,stroke-width:1px;
    classDef success  fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    subgraph A["дані"]
        direction LR
        S1["1 · типи<br>і Pydantic"] --> S2["2 · FastAPI"] --> S3["3 · SQLAlchemy<br>і Alembic"] --> S4["4 · middleware<br>і Redis"]
    end
    subgraph B["якість і можливості"]
        direction LR
        S5["5 · тести"] --> S6["6 · AI-інструменти"] --> S7["7 · LLM API"] --> S8["8 · безпека"] --> S9["9 · Telegram-бот"]
    end
    subgraph C["production"]
        direction LR
        S10["10 · Docker"] --> S11["11 · Compose<br>і деплой"] --> S12["12 · CI/CD"]
    end
    A --> B --> C

    class S1,S2,S3,S4,S5,S6,S7,S8,S9,S10,S11 step
    class S12 success
```

| Крок | Що додається | Тестів |
|---|---|---|
| [0. Що таке API](00_first_api/index.md) | клієнт і сервер, перший API на 13 рядків, перевірка знань | — |
| [1. Типи і Pydantic](01_typing_pydantic/index.md) | анотації типів, `NewsItem`, `validate_news` | 12 |
| [2. Перший API на FastAPI](02_fastapi_basics/index.md) | `GET /api/news`, `POST /api/scrape`, `Depends`, `/docs`, Postman | 23 |
| [3. SQLAlchemy і Alembic](03_sqlalchemy_alembic/index.md) | база, репозиторій, CRUD, міграції | 32 |
| [4. Middleware, кеш і Redis](04_middleware_redis/index.md) | middleware, кеш, rate limit, фоновий збір | 41 |
| [5. Тестування API](05_api_testing/index.md) | unit / integration, фікстури, моки, фейки, покриття | 86 |
| [6. AI-інструменти](06_ai_dev_tools/index.md) | Claude Code, RSS-джерело, написане AI за тестами | 107 |
| [7. LLM API](07_llm_api/index.md) | аналіз новин Gemini / Anthropic, circuit breaker | 168 |
| [8. Безпека](08_security/index.md) | JWT адміна, SSRF, підписані webhook | 279 |
| [9. Telegram-бот](09_telegram_bot/index.md) | aiogram, підписки, polling і webhook | 335 |
| [10. Docker](10_docker/index.md) | образ, HEALTHCHECK, `/health/ready` | 340 |
| [11. Compose і деплой](11_compose_deploy/index.md) | nginx, PostgreSQL, Redis, міграції, бекап | 343 |
| [12. CI/CD](12_ci_cd/index.md) | GitHub Actions, mypy, smoke, ghcr.io | 343 |

«Тестів» — скільки проходить `pytest -q` у папці кроку (без тестів, що потребують Docker або справжнього LLM).

Ніколи не писав API? Почни з [кроку 0](00_first_api/index.md): там пояснено простими словами, що таке клієнт, сервер і API, ти запустиш перший сервер на 13 рядків і [перевіриш себе](00_first_api/readiness.md) перед кроком 1. Перед стартом — [Налаштування](../00_getting_started/local_setup.md).
