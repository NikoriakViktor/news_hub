# HTTP-клієнти: requests, httpx, aiohttp

Кожен скрипт сам запускає локальний сервер `server.py` (FastAPI + uvicorn, `127.0.0.1:8741`) у фоновому
потоці: повільні відповіді, збої `503`, перенаправлення, старе кодування, великі файли. Інтернет не потрібен.

```bash
pip install -r requirements.txt
python basics.py               # той самий GET трьома бібліотеками, raise_for_status, User-Agent
python timeouts.py             # без тайм-ауту, connect / read / total, тіло, що «капає»
python pooling.py              # одне з'єднання на багато запитів; клієнт на кожен запит — повільно
python retries.py              # backoff + jitter, Retry-After, чому POST не повторюють
python redirects_encodings.py  # хто йде за перенаправленням сам; bytes → str, charset, битий байт
python streaming.py            # великі відповіді частинами і стеля розміру (Linux: resource)
python concurrency.py          # по черзі, gather, Semaphore, ліміти пулу, PoolTimeout
python api_client.py           # свій клас-клієнт до чужого API
pytest -q test_clients.py      # MockTransport, ASGITransport, справжній aiohttp проти локального сервера
```

Час у виводі залежить від машини. Розбір — сторінка книги «HTTP-клієнти» (Частина I).
