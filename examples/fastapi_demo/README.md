# fastapi_demo — async чи blocking: що витримає сервер

Стартовий код прототипу `fastapi_demo` без змін логіки.
Шість ендпоінтів, що роблять одне й те саме — чекають 2 с або рахують — але по-різному:

| Ендпоінт | Як написаний | Що з сервером |
|---|---|---|
| `/sync-broken` | `async def` + `time.sleep(2)` | event loop стоїть — запити йдуть по одному |
| `/sync-safe` | `def` + `time.sleep(2)` | FastAPI виконує в пулі потоків (40) |
| `/async-correct` | `async def` + `await asyncio.sleep(2)` | усі запити чекають одночасно |
| `/cpu-broken` | `async def` + цикл обчислень | event loop стоїть на час обчислення |
| `/cpu-fixed` | `run_in_executor(ProcessPoolExecutor)` | обчислення в іншому процесі |
| `/db-sync-broken/{id}`, `/db-async-correct/{id}` | «синхронний драйвер БД» без / з `run_in_executor` | те саме на прикладі бази |

## Запуск

```bash
pip install -r app/requirements.txt aiohttp   # aiohttp — клієнт load_test.py
uvicorn app.main:app --port 8001     # з цієї папки
python load_test.py                  # в іншому терміналі: 5 тестів, Enter між ними
```

Або `docker compose up --build` — API на http://localhost:8001/docs, Streamlit-панель на http://localhost:8534.

Розбір — [Крок 2 у книзі: async чи blocking](https://nikoriakviktor.github.io/news_hub/tutorials/02_fastapi_basics/async_measurements/).
