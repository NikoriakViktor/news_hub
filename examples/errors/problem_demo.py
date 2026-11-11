import json

from fastapi.testclient import TestClient

from problem_app import app

c = TestClient(app, raise_server_exceptions=False)
for label, r in [
    ("raise HTTPException(404)", c.get("/items/7")),
    ("невідомий маршрут", c.get("/nope")),
    ("не той метод", c.delete("/items/7")),
    ("короткий пароль, email без @", c.post("/signup", json={"email": "ab.c", "password": "hunter2"})),
    ("401", c.get("/private")),
    ("необроблений виняток", c.get("/boom")),
]:
    extra = f" www-authenticate={r.headers['www-authenticate']}" if "www-authenticate" in r.headers else ""
    print(f"--- {label}: {r.status_code} {r.headers['content-type']}{extra}")
    print(json.dumps(r.json(), ensure_ascii=False))
s = c.get("/openapi.json").json()["paths"]["/signup"]["post"]["responses"]["422"]
print("--- OpenAPI 422:", s["description"], list(s["content"]), s["content"]["application/problem+json"]["schema"]["title"])
