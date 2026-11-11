"""Ті самі дані через три способи версіонування; що бачить клієнт і що потрапляє в OpenAPI."""
from fastapi import APIRouter
from fastapi.testclient import TestClient

from versioning_app import app

c = TestClient(app)
print("Шлях:")
for url in ["/api/v1/users/1", "/api/v2/users/1", "/api/v3/users/1"]:
    r = c.get(url)
    print(f"  {url:18} {r.status_code} {r.json()}")
r = c.get("/api/v1/users/1")
print("  заголовки v1:", {k: r.headers[k] for k in ("deprecation", "sunset", "link")})

print("Заголовок:")
for headers in [{}, {"X-API-Version": "1"}, {"X-API-Version": "3"}]:
    r = c.get("/users/1", headers=headers)
    print(f"  {str(headers):26} {r.status_code} {r.json()}  vary={r.headers.get('vary')}")

print("Параметр:")
for url in ["/q/users/1?version=1", "/q/users/1"]:
    print(f"  {url:22} {c.get(url).json()}")

schema = c.get("/openapi.json").json()
print("OpenAPI:")
for path, ops in schema["paths"].items():
    op = ops["get"]
    resp = op["responses"]["200"]["content"]["application/json"]["schema"]
    print(f"  {path:24} deprecated={op.get('deprecated', False)!s:5} 200 → {resp.get('$ref', resp).__str__()[:70]}")

print("prefix з косою рискою в кінці:")
try:
    APIRouter(prefix="/v1/")
except AssertionError as error:
    print("  AssertionError:", error)
