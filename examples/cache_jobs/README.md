# Middleware, кеш, rate limit і фонові задачі

```bash
pip install -r requirements.txt
python middleware_demo.py        # три способи написати middleware, порядок, чого middleware не бачить, GZip/TrustedHost/HTTPSRedirect
python redis_demo.py             # TTL, структури даних, гонитва, pipeline, MULTI без відкату, WATCH, Lua, SCAN, fakeredis
python cache_demo.py             # cache-aside, інвалідація (DEL, версія, теги), гонитва з записом, stampede, розкид TTL
python rate_limit_demo.py        # фіксоване/ковзне вікно, ковзний лічильник, token bucket; 429; X-Forwarded-For
python background_jobs_demo.py   # BackgroundTasks зсередини, перезапуск uvicorn, надійна черга, повтори, ідемпотентність
```

Без параметрів демо працюють на `fakeredis` — Redis у пам'яті процесу. Частина ефектів (гонитва між
клієнтами, затримка мережі) видна лише на справжньому сервері. Тимчасовий Redis у Docker:

```bash
docker run --rm -d --name part06-redis -p 6390:6379 redis:7-alpine
REDIS_URL=redis://localhost:6390/0 python redis_demo.py
REDIS_URL=redis://localhost:6390/0 python rate_limit_demo.py
REDIS_URL=redis://localhost:6390/0 python arq_demo.py   # черга arq: лише зі справжнім Redis
docker stop part06-redis                                # --rm: контейнер видалиться сам
```

Демо пишуть лише ключі з префіксами `demo:` і `arq:` і прибирають їх за собою; не запускай їх на Redis з даними.
`background_jobs_demo.py` запускає uvicorn на порту `18765`.

Розбір — Частина VI книги: «Middleware», «Redis для API», «Стратегії кешу», «Rate limit», «Фонові задачі й черги».
