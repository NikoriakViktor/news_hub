# HTTP зсередини

Приклади до Частини I книги. Кожен файл запускається окремо.

| Файл | Що показує | Сторінка книги |
|---|---|---|
| `inspect_app.py` + `raw_client.py` | сирий HTTP через сокет: стартовий рядок, заголовки, тіло; `307`, `405`, `422` | [HTTP-запит і відповідь](https://nikoriakviktor.github.io/news_hub/01_http_and_rest/http_anatomy/) |
| `methods_app.py` + `methods_demo.py` | повтори `POST`, `PUT`, `PATCH`, `DELETE`; зайві поля; `HEAD` | [Методи HTTP](https://nikoriakviktor.github.io/news_hub/01_http_and_rest/http_methods/) |
| `codes_app.py` | що FastAPI відповідає сам: битий JSON, `500`, `204`, `401` | [Коди відповідей](https://nikoriakviktor.github.io/news_hub/01_http_and_rest/status_codes/) |
| `cache_app.py` + `cache_demo.py` | `Cache-Control`, `ETag`, `304 Not Modified` | [Принципи REST](https://nikoriakviktor.github.io/news_hub/01_http_and_rest/rest_principles/) |

```bash
pip install fastapi uvicorn httpx
uvicorn inspect_app:app --port 8014     # і в іншому терміналі: python raw_client.py
python methods_demo.py
python cache_demo.py
```
