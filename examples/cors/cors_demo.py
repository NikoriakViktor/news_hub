"""Перевірка CORS без браузера: TestClient надсилає те, що надіслав би браузер, а browser_reads() перевіряє відповідь
так, як це робить браузер (специфікація Fetch, «CORS check»)."""
import os

from fastapi.testclient import TestClient

from cors_app import Settings, create_app

UI = "https://ui.example.com"
EVIL = "https://evil.example"
COOKIE = {"Cookie": "session_id=s3cr3t"}


def browser_reads(response, origin: str, credentials: bool) -> bool:
    """Чи віддасть браузер відповідь скрипту зі сторінки origin."""
    allow_origin = response.headers.get("access-control-allow-origin")
    if credentials:
        return allow_origin == origin and response.headers.get("access-control-allow-credentials") == "true"
    return allow_origin in ("*", origin)


def cors_headers(response) -> dict:
    return {k: v for k, v in response.headers.items() if k.startswith("access-control") or k == "vary"}


def preflight(client, origin: str, method: str, headers: str | None = None):
    request_headers = {"Origin": origin, "Access-Control-Request-Method": method}
    if headers:
        request_headers["Access-Control-Request-Headers"] = headers
    return client.options("/api/me", headers=request_headers)


safe = TestClient(create_app([UI]), raise_server_exceptions=False)

print("--- 1. preflight з UI: DELETE + Authorization")
response = preflight(safe, UI, "DELETE", "authorization,content-type")
print(response.status_code, response.text, cors_headers(response))

print("--- 2. preflight з чужого сайту")
response = preflight(safe, EVIL, "DELETE", "authorization")
print(response.status_code, response.text)

print("--- 3. preflight із заголовком, якого немає в allow_headers")
response = preflight(safe, UI, "GET", "x-custom-token")
print(response.status_code, response.text)

print("--- 4. GET /api/me з cookie: UI і чужий сайт")
for origin in (UI, EVIL):
    response = safe.get("/api/me", headers={"Origin": origin, **COOKIE})
    print(f"{origin}: {response.status_code} {response.text}  браузер віддасть скрипту: "
          f"{browser_reads(response, origin, credentials=True)}")

print("--- 5. «проста» форма POST з чужого сайту: preflight не потрібен")
response = safe.post("/api/transfer", data={"amount": 500}, headers={"Origin": EVIL, **COOKIE})
print(response.status_code, "браузер віддасть скрипту:", browser_reads(response, EVIL, credentials=True),
      "| переказів на сервері:", safe.get("/api/transfers").json()["transfers"])

print("--- 6. allow_origins з косою рискою в кінці")
slash = TestClient(create_app([UI + "/"]))
response = slash.get("/api/me", headers={"Origin": UI, **COOKIE})
print(response.status_code, "allow-origin:", response.headers.get("access-control-allow-origin"))

print("--- 7. помилки: 401, 500, 429")
for path, extra in (("/api/me", {}), ("/api/boom", {}), ("/api/me", {"X-Flood": "1"})):
    response = safe.get(path, headers={"Origin": UI, **extra})
    print(f"{path} {extra or ''} → {response.status_code}, allow-origin: {response.headers.get('access-control-allow-origin')}")
outer_limit = TestClient(create_app([UI], limit_after_cors=True))
response = outer_limit.get("/api/me", headers={"Origin": UI, "X-Flood": "1"})
print(f"rate limit доданий після CORS → {response.status_code}, allow-origin: {response.headers.get('access-control-allow-origin')}")

print('--- 8. allow_origins=["*"] + allow_credentials=True')
star = TestClient(create_app(["*"], credentials=True))
response = star.get("/api/me", headers={"Origin": EVIL, **COOKIE})
print(response.status_code, response.text, cors_headers(response))
print("браузер віддасть скрипту з evil.example:", browser_reads(response, EVIL, credentials=True))
response = preflight(star, EVIL, "DELETE", "authorization")
print("preflight з evil.example:", response.status_code, response.headers.get("access-control-allow-origin"))

print('--- 9. allow_origins=["*"] без credentials')
public = TestClient(create_app(["*"], credentials=False))
response = public.get("/api/me", headers={"Origin": EVIL, **COOKIE})
print(response.status_code, cors_headers(response))
print("з cookie (credentials: 'include'):", browser_reads(response, EVIL, credentials=True),
      "| без cookie:", browser_reads(response, EVIL, credentials=False))

print("--- 10. список джерел зі змінної середовища")
os.environ["CORS_ORIGINS"] = "https://ui.example.com/, http://localhost:3000"
print(Settings().cors_origins)
