# Частина VI. Middleware, кеш і фонові задачі

Код навколо кожного запиту, кеш у Redis (cache-aside з версією), обмеження частоти запитів і фонові задачі зі статусом.

## Розділи

| Розділ | Код | Стан |
|---|---|---|
| [Middleware](middleware.md) | `steps/04/news_hub/middleware.py` | готово |
| [CORS](cors.md) | `examples/cors/cors_app.py`, `cors_demo.py` | готово |
| [Redis для API](redis_basics.md) | `examples/cache_jobs/redis_demo.py` | готово |
| [Стратегії кешу](caching.md) | `steps/04/news_hub/cache.py` | готово |
| [Rate limit](rate_limiting.md) | — | готово |
| [Фонові задачі й черги](background_jobs.md) | `steps/04/news_hub/jobs.py` | готово |

## На практиці — Zero to Hero

- [Крок 4. Middleware, кеш і Redis](../tutorials/04_middleware_redis/index.md) — `steps/04_middleware_redis`
