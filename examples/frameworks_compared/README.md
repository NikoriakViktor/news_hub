# FastAPI, Flask і Django: той самий API

Два ендпоінти нотаток (`GET /api/notes?limit=`, `POST /api/notes`) з однаковими правилами на трьох фреймворках:

- `fastapi_app.py` — перевірку робить Pydantic за анотаціями типів;
- `flask_app.py` — дані з `request` і перевірка вручну;
- `django_app.py` — URLConf + view + `forms.Form`, без DRF (один файл заради порівняння);
- `compare.py` — однакові запити до всіх трьох через їхні тестові клієнти.

```bash
pip install -r requirements.txt
python compare.py
```

Розбір — [FastAPI, Flask і Django](https://nikoriakviktor.github.io/news_hub/03_fastapi_core/fastapi_flask_django/).
