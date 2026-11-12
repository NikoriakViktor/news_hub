# Довідник

Сторінки для швидкого пошуку: таблиці, короткі фрагменти коду, що запускаються, і посилання на розділ, де тему
розібрано повністю. Читати довідник по черзі не треба: відкривай, коли потрібно згадати синтаксис, код відповіді,
змінну середовища чи причину помилки.

## Розділи { #pages }

| Сторінка | Що там | Звідки дані |
|---|---|---|
| [Шпаргалка FastAPI](fastapi_cheatsheet.md) | маршрути, параметри, відповіді, `Depends`, `lifespan`, middleware, обробники винятків, `APIRouter`, `BackgroundTasks`, тести | [`examples/reference/cheatsheet_check.py`](https://github.com/NikoriakViktor/news_hub/blob/main/examples/reference/cheatsheet_check.py) |
| [Шпаргалка Pydantic](pydantic_cheatsheet.md) | `Field`, валідатори, `ConfigDict`, серіалізація, типи, налаштування | той самий скрипт |
| [Архітектура й production](architecture.md) | ASGI і WSGI, три типи ендпоінтів, блокуючий код, пул з'єднань, Repository, Unit of Work, мікросервіси, чекліст перед деплоєм | виміри на FastAPI 0.162 і PostgreSQL 16 |
| [Від Django до FastAPI](django_to_fastapi.md) | що в Django/DRF відповідає чому у FastAPI, SQLAlchemy і Pydantic | код `steps/12_ci_cd`, `examples/fastapi_vs_drf` |
| [Коди відповідей News Hub](http_status_codes.md) | кожен код, який повертає API, і коли саме | `steps/12_ci_cd/news_hub/api.py`, OpenAPI-схема, запуск |
| [Змінні середовища](env_vars.md) | усі змінні фінальної версії: значення за замовчуванням, хто читає, з якого кроку | `grep` по `steps/` |
| [Команди](commands.md) | запуск, тести, маркери, mypy, Alembic, Docker, Compose, скрипти | README кроків, CI |
| [Глосарій](glossary.md) | терміни книги з посиланнями | — |
| [Типові помилки](troubleshooting.md) | повідомлення → причина → що зробити → де розібрано | розділи «Типові помилки» кроків і частин |

У роботі: довідник Claude Code (встановлення, `CLAUDE.md`, дозволи, hooks, skills, MCP, безпека) — до того
часу див. [крок 6](../tutorials/06_ai_dev_tools/index.md).

## Версії { #versions }

Фрагменти перевірено на FastAPI 0.162, Starlette 1.10, Pydantic 2.13, pydantic-settings 2.16, uvicorn 0.54,
SQLAlchemy 2.1. Найнижчі версії, з якими працює сам News Hub, — у
[`steps/12_ci_cd/requirements.txt`](https://github.com/NikoriakViktor/news_hub/blob/main/steps/12_ci_cd/requirements.txt);
їх перевіряє CI ([мінімальні версії, крок 5](../tutorials/05_api_testing/min_versions.md)).

## Зовнішня документація { #external }

- [FastAPI](https://fastapi.tiangolo.com/) · [Starlette](https://starlette.dev/) · [Pydantic](https://docs.pydantic.dev/latest/) · [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [SQLAlchemy 2](https://docs.sqlalchemy.org/en/20/) · [Alembic](https://alembic.sqlalchemy.org/) · [uvicorn](https://uvicorn.dev/)
- [Redis](https://redis.io/docs/latest/) · [aiogram](https://docs.aiogram.dev/) · [pytest](https://docs.pytest.org/) · [HTTPX](https://www.python-httpx.org/)
- [Docker](https://docs.docker.com/) · [GitHub Actions](https://docs.github.com/en/actions)
- Django-книга [Notes Chat App](https://nikoriakviktor.github.io/notes_chat_app/) — ті самі теми на Django і DRF
