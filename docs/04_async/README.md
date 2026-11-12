# Частина IV. Async і конкурентність

ASGI проти WSGI, три типи ендпоінтів і що з ними робить FastAPI, чому один блокуючий виклик гальмує всіх, як паралельно забрати десять сторінок (`asyncio.gather`) і як це виміряти.

## Розділи

| Розділ | Код | Стан |
|---|---|---|
| [Чекати чи рахувати](concurrency_basics.md) | `examples/async_concurrency/basics_demo.py` | готово |
| [ASGI і WSGI](asgi_vs_wsgi.md) | — | готово |
| [Три типи ендпоінтів](endpoint_types.md) | — | готово |
| [Блокуючий код: каскадний ефект](blocking_code.md) | — | готово |
| [Паралельні запити](concurrency_patterns.md) | `steps/02/news_hub/scraper.py` | готово |

## На практиці — Zero to Hero

- [Крок 2. Перший API на FastAPI](../tutorials/02_fastapi_basics/index.md) — `steps/02_fastapi_basics`
- [Крок 4. Middleware, кеш і Redis](../tutorials/04_middleware_redis/index.md) — `steps/04_middleware_redis`
