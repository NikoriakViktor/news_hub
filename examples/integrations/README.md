# Інтеграції: LLM API, Telegram-бот, WebSocket, hooks Claude Code

```bash
pip install -r requirements.txt
python llm_api_demo.py          # що SDK надсилає в мережу, схема відповіді, перевірка Pydantic, stop_reason, вартість
python llm_reliability_demo.py  # тайм-аут, повтори з backoff, повтори SDK, пул моделей, breaker, кеш, ін'єкція
python telegram_demo.py         # aiogram: фільтри, middleware, FSM, inline-кнопки, помилки Bot API, webhook у FastAPI
python ws_demo.py               # два сервери uvicorn: Origin, токен, MemoryHub проти RedisHub
pytest -q                       # тести всіх прикладів і hook
```

**Мережі немає.** Справжні LLM API й Telegram не викликаються:

- `anthropic` отримує `http_client` з `MockTransport` — запит, який SDK зібрав би, обробляє функція в демо;
- `FakeLLM` (`llm_kit.py`) відповідає за сценарієм і записує промпти;
- `FakeTelegram` (`telegram_demo.py`) — сесія aiogram, яка записує виклики Bot API й повертає JSON у форматі Bot API;
- `ws_demo.py` піднімає два сервери uvicorn на `127.0.0.1`; Redis — fakeredis або `REDIS_URL=redis://…`.

`claude_hooks/protect_paths.py` — PreToolUse-hook для Claude Code; `claude_hooks/test_protect_paths.py` перевіряє
його без агента. Розбір — Частина IX книги.
