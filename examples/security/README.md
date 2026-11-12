# Безпека API у FastAPI: приклади

```bash
pip install -r requirements.txt
python passwords_demo.py     # sha256 проти bcrypt і Argon2, сіль, вартість, 72 байти, перехешування, сталий час
python auth_demo.py          # OAuth2PasswordBearer, access + refresh, ротація, відкликання, сесія в cookie, CSRF
python authz_demo.py         # scopes, BOLA, масове присвоєння, BFLA, надмірні дані, два входи (API і бот)
python owasp_demo.py         # OWASP API4, API8, API9, API10
python ssrf_demo.py          # які адреси внутрішні, denylist рядків, два парсери, DNS rebinding, сліпий SSRF
python webhooks_demo.py      # підписи в стилі GitHub і Stripe, повтори, ротація секрету, Telegram
python headers_demo.py       # слабкий секрет JWT, kid, заголовки, TrustedHost, проксі, журнали, ліміт входу
```

Застосунки (`auth_app.py`, `authz_app.py`) — фабрики `create_app(...)`: секрети й паролі передає скрипт, який
їх створює, і кожен скрипт генерує одноразові (`secrets`). Запити йдуть через `TestClient` або
`httpx.ASGITransport`; «внутрішній сервіс» у `ssrf_demo.py` — локальний сервер на `127.0.0.1`, DNS підмінено.
Жоден скрипт не звертається в інтернет. Кожна вразливість показана на прикладі поруч зі своїм виправленням
(`/v1` — як буває, `/v2` — як треба) і лише проти цих локальних застосунків.

Starlette 1.x з `httpx` друкує в stderr `StarletteDeprecationWarning` про `httpx2`: на результат не впливає.

Розбір — Частина VIII книги «Безпека API».
