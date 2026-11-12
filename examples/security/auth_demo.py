"""Автентифікація: Bearer JWT (access + refresh, ротація, відкликання) і сесія в cookie (CSRF).

python auth_demo.py — секрет і пароль генеруються тут; лише TestClient, без мережі.
"""
import base64
import json
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from auth_app import ALGORITHM, create_app

SECRET = secrets.token_urlsafe(48)
PASSWORD = secrets.token_urlsafe(12)
app = create_app(SECRET, {"olena": PASSWORD}, emails={"olena": "olena@example.com"})
api = TestClient(app, base_url="https://testserver")


def title(text: str) -> None:
    print(f"--- {text}")


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def show(label: str, response) -> None:
    body = response.json() if response.content else ""
    print(f"   {label:34} → {response.status_code} {body}")


def b64json(part: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


title("1. OAuth2PasswordBearer в OpenAPI")
print("  ", app.openapi()["components"]["securitySchemes"])

title("2. без токена і вхід формою")
r = api.get("/me")
print(f"   GET /me без токена                 → {r.status_code} {r.json()} WWW-Authenticate: {r.headers['www-authenticate']}")
show("POST /token, JSON замість форми", api.post("/token", json={"username": "olena", "password": PASSWORD}))
show("POST /token, чужий пароль", api.post("/token", data={"username": "olena", "password": "guess"}))
pair = api.post("/token", data={"username": "olena", "password": PASSWORD}).json()
header, payload, _ = pair["access_token"].split(".")
print("   header  без ключа:", b64json(header))
claims = b64json(payload)
print("   payload без ключа:", {k: claims[k] for k in ("sub", "type", "ver")}, "| живе", claims["exp"] - claims["iat"], "с")
show("GET /me з access", api.get("/me", headers=bearer(pair["access_token"])))
show("GET /me з refresh замість access", api.get("/me", headers=bearer(pair["refresh_token"])))

title("3. ротація refresh і повторне використання")
new = api.post("/refresh", json={"refresh_token": pair["refresh_token"]}).json()
print("   POST /refresh                      → нова пара, refresh змінився:", new["refresh_token"] != pair["refresh_token"])
show("той самий старий refresh ще раз", api.post("/refresh", json={"refresh_token": pair["refresh_token"]}))
show("новий refresh після цього", api.post("/refresh", json={"refresh_token": new["refresh_token"]}))
show("новий access після цього", api.get("/me", headers=bearer(new["access_token"])))

title("4. вихід: сервер пам'ятає відкликане")
pair = api.post("/token", data={"username": "olena", "password": PASSWORD}).json()
other = api.post("/token", data={"username": "olena", "password": PASSWORD}).json()     # другий пристрій
api.post("/logout", headers=bearer(pair["access_token"]))
show("access після /logout", api.get("/me", headers=bearer(pair["access_token"])))
show("refresh після /logout", api.post("/refresh", json={"refresh_token": pair["refresh_token"]}))
show("другий пристрій", api.get("/me", headers=bearer(other["access_token"])))
print("   відкликаних родин на сервері:", len(app.state.store.revoked_families))
api.post("/logout-all", headers=bearer(other["access_token"]))
show("другий пристрій після /logout-all", api.get("/me", headers=bearer(other["access_token"])))

title("5. строк дії і leeway")
now = datetime.now(timezone.utc)
late = jwt.encode({"sub": "olena", "exp": now - timedelta(seconds=10)}, SECRET, algorithm=ALGORITHM)
for leeway in (0, 30):
    try:
        jwt.decode(late, SECRET, algorithms=[ALGORITHM], leeway=leeway)
        print(f"   прострочений на 10 с, leeway={leeway:2} → прийнято")
    except jwt.ExpiredSignatureError as error:
        print(f"   прострочений на 10 с, leeway={leeway:2} → {type(error).__name__}")

title("6. сесія в cookie")
r = api.post("/session", data={"username": "olena", "password": PASSWORD})
print("   Set-Cookie:", r.headers["set-cookie"].split("=", 1)[0], "…;", r.headers["set-cookie"].split(";", 1)[1].strip())
show("GET /session/me (cookie сам)", api.get("/session/me"))
plain = TestClient(app)                                               # http://testserver, не https://
plain.post("/session", data={"username": "olena", "password": PASSWORD})
print("   по http: cookie є в клієнті:", "sid" in plain.cookies, "| надіслано з запитом → GET /session/me",
      plain.get("/session/me").status_code)
api.delete("/session")
show("після DELETE /session", api.get("/session/me"))

title("7. CSRF: дія з cookie і чужий сайт")
api.post("/session", data={"username": "olena", "password": PASSWORD})
for origin in ("https://evil.example", "https://app.example.com"):
    show(f"transfer, Origin {origin}", api.post("/session/transfer", headers={"Origin": origin}))
    show(f"transfer-safe, Origin {origin}", api.post("/session/transfer-safe", headers={"Origin": origin}))
show("transfer-safe без Origin", api.post("/session/transfer-safe"))
api.cookies.clear()
show("Bearer-ендпоінт без заголовка", api.get("/me", headers={"Origin": "https://evil.example"}))

title("8. скидання пароля")
for email in ("olena@example.com", "nobody@example.com"):
    show(f"POST /password-reset {email}", api.post("/password-reset", json={"email": email}))
outbox = app.state.store.outbox
print("   листів:", len(outbox), "| кому:", [to for to, _ in outbox])
link = outbox[0][1]
reset_token = link.split("token=", 1)[1]
print("   посилання:", link.split("?")[0] + "?token=…", "| type:", b64json(reset_token.split(".")[1])["type"])
pair = api.post("/token", data={"username": "olena", "password": PASSWORD}).json()
NEW = secrets.token_urlsafe(12)
show("reset-токен як access", api.get("/me", headers=bearer(reset_token)))
r = api.post("/password-reset/confirm", json={"token": reset_token, "new_password": NEW})
print(f"   {'confirm':34} → {r.status_code}")
show("те саме посилання вдруге", api.post("/password-reset/confirm", json={"token": reset_token, "new_password": "x"}))
show("access, виданий до зміни пароля", api.get("/me", headers=bearer(pair["access_token"])))
show("вхід зі старим паролем", api.post("/token", data={"username": "olena", "password": PASSWORD}))
print(f"   {'вхід з новим паролем':34} →", api.post("/token", data={"username": "olena", "password": NEW}).status_code)
