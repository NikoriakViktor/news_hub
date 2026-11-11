"""Ті самі запити до трьох застосунків через їхні тестові клієнти. Запуск: python compare.py"""
import json

from fastapi.testclient import TestClient

import django_app  # noqa: F401 — налаштовує Django
import django
django.setup()
from django.test import Client  # noqa: E402

import fastapi_app  # noqa: E402
import flask_app    # noqa: E402

fast, flask, dj = TestClient(fastapi_app.app), flask_app.app.test_client(), Client()


def show(name, status, body):
    if isinstance(body, dict) and "detail" in body:          # FastAPI: лише місце й текст кожної помилки
        body = [(e["loc"], e["msg"]) for e in body["detail"]]
        print(f"  {name:8} {status}  {body}")
        return
    print(f"  {name:8} {status}  {json.dumps(body, ensure_ascii=False)}")


CASES = [
    ("POST добра", "post", "/api/notes", {"title": "Купити каву", "priority": 2}),
    ('POST погана  {"title": "", "priority": 9}', "post", "/api/notes", {"title": "", "priority": 9}),
    ("GET limit=abc", "get", "/api/notes?limit=abc", None),
    ("GET limit=1", "get", "/api/notes?limit=1", None),
]
for title, method, url, body in CASES:
    print(title)
    r = fast.post(url, json=body) if method == "post" else fast.get(url)
    show("FastAPI", r.status_code, r.json())
    r = flask.post(url, json=body) if method == "post" else flask.get(url)
    show("Flask", r.status_code, r.get_json())
    r = dj.post(url, json.dumps(body), content_type="application/json") if method == "post" else dj.get(url)
    show("Django", r.status_code, r.json())

print("OpenAPI:")
print("  FastAPI ", fast.get("/openapi.json").status_code, sorted(fast.get("/openapi.json").json()["paths"]))
print("  Flask   ", flask.get("/openapi.json").status_code)
print("  Django  ", dj.get("/openapi.json").status_code)
