from fastapi.testclient import TestClient

from naive_app import app

c = TestClient(app, raise_server_exceptions=False)
for label, r in [
    ("raise HTTPException(404)", c.get("/items/1")),
    ("невідомий маршрут      ", c.get("/nope")),
    ("не той метод           ", c.delete("/items/1")),
    ("короткий пароль        ", c.post("/signup", json={"email": "a@b.c", "password": "hunter2"})),
    ("email без @ (ValueError)", c.post("/signup", json={"email": "ab.c", "password": "x" * 12})),
]:
    print(f"{label} → {r.status_code} {r.headers['content-type']:32} {r.text[:150]}")
