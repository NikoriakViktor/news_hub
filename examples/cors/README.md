# CORS у FastAPI

```bash
pip install -r requirements.txt
python cors_demo.py
```

`cors_demo.py` надсилає запити так, як їх надіслав би браузер (`Origin`, preflight `OPTIONS`), і перевіряє відповідь за правилами браузера: preflight, `["*"]` разом з `allow_credentials`, коса риска в джерелі, помилки без заголовків CORS, порядок middleware, список джерел зі змінної `CORS_ORIGINS`.

Розбір — сторінка книги «CORS» (Частина VI).
