"""Перший запит, повтор з If-None-Match, повтор після зміни. Запуск: python cache_demo.py"""
from fastapi.testclient import TestClient

from cache_app import ARTICLES, app

c = TestClient(app)
r1 = c.get("/articles/rest")
print("1 →", r1.status_code, r1.headers["etag"], r1.headers["cache-control"], len(r1.content), "байтів")
r2 = c.get("/articles/rest", headers={"If-None-Match": r1.headers["etag"]})
print("2 →", r2.status_code, r2.headers["etag"], len(r2.content), "байтів")
ARTICLES["rest"]["title"] = "Принципи REST (оновлено)"
r3 = c.get("/articles/rest", headers={"If-None-Match": r1.headers["etag"]})
print("3 →", r3.status_code, r3.headers["etag"], r3.json())
print("/me →", c.get("/me").headers["cache-control"])
