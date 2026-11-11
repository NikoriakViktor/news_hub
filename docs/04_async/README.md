# Частина IV. Async і конкурентність

ASGI проти WSGI, три типи ендпоінтів і що з ними робить FastAPI, чому один блокуючий виклик гальмує всіх, як паралельно забрати десять сторінок (`asyncio.gather`) і як це виміряти.

## Розділи

| Розділ | Джерело | Стан |
|---|---|---|
| ASGI і WSGI | `fastapi_documentation.md` §2 | у роботі |
| Три типи ендпоінтів | `fastapi_documentation.md` §3 | у роботі |
| Блокуючий код: каскадний ефект | `fastapi_documentation.md` §4 | у роботі |
| Паралельний збір і виміри | урок 38 «Async чи blocking: виміри»; `steps/02/news_hub/scraper.py` | у роботі |

## На практиці — Zero to Hero

- [Крок 2. Перший API на FastAPI](../tutorials/02_fastapi_basics/index.md) — `steps/02_fastapi_basics`
- [Крок 4. Middleware, кеш і Redis](../tutorials/04_middleware_redis/index.md) — `steps/04_middleware_redis`
