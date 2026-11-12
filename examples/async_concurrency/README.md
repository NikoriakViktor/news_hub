# Async і конкурентність: виміри

Python 3.11+ (`patterns_demo.py` використовує `asyncio.TaskGroup` і `asyncio.timeout`). Інтернет не потрібен:
кожне демо саме запускає локальні сервери (uvicorn окремими процесами на портах 8771–8795) і зупиняє їх.

```bash
pip install -r requirements.txt
python basics_demo.py           # чекати чи рахувати: послідовно, потоки, процеси, asyncio; гонитва; ціна потоку і задачі
python asgi_wsgi_demo.py        # інтерфейси WSGI і ASGI; wsgiref проти uvicorn; --workers 2; --limit-concurrency
python endpoint_types_demo.py   # async def / def / блокуючий виклик; пул потоків на 40; run_in_threadpool і asyncio.to_thread
python blocking_demo.py         # каскадний ефект; requests → httpx, процесор → ProcessPool, bcrypt → потік; PYTHONASYNCIODEBUG
python patterns_demo.py         # gather, return_exceptions, TaskGroup, Semaphore, тайм-аути, скасування, as_completed
```

| Файл | Що це |
|---|---|
| `serve.py` | запускає сервер окремим процесом і чекає, поки порт прийме з'єднання |
| `wsgi_app.py`, `asgi_app.py` | найменші WSGI- і ASGI-застосунки без фреймворку |
| `endpoint_types_app.py` | той самий «повільний виклик» у шести видах ендпоінтів; `THREAD_LIMIT` змінює пул потоків |
| `upstream_app.py` | локальне «джерело новин»: затримки, `503`, лічильник одночасних запитів |
| `blocking_app.py` | блокуючі виклики (мережа, процесор, bcrypt) і їхні заміни; `/lag` — затримка циклу подій |

Час залежить від машини й навантаження; співвідношення між рядками — ні. Розбір — Частина IV книги
«Async і конкурентність».
