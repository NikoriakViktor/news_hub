"""Повтори запитів: що змінюється на сервері. Запуск: python methods_demo.py"""
from fastapi.testclient import TestClient

from methods_app import ITEMS, app

c = TestClient(app)
book = {"title": "Книга", "description": "FastAPI"}


def state() -> str:
    return str(list(ITEMS.values()))


print("POST ×2  →", c.post("/items", json=book).status_code, c.post("/items", json=book).status_code)
print("  стан:", state())
print("  Location:", c.post("/items", json={"title": "Третя"}).headers["location"])
print("PUT ×2 /items/1 {title} →", [c.put("/items/1", json={"title": "Нова"}).json() for _ in range(2)])
print("PATCH /items/2 {title} →", c.patch("/items/2", json={"title": "Друга"}).json())
print("DELETE ×2 /items/3 →", c.delete("/items/3").status_code, c.delete("/items/3").status_code)
print("  стан:", state())
print("POST з id і is_admin →", c.post("/items", json={"title": "x", "id": 999, "is_admin": True}).json())
r = c.post("/strict-items", json={"title": "x", "id": 999})
print("strict  з id         →", r.status_code, [(e["loc"], e["msg"]) for e in r.json()["detail"]])
for method in ("HEAD", "OPTIONS"):
    r = c.request(method, "/items")
    print(f"{method:7} /items →", r.status_code, r.headers.get("allow", ""))
