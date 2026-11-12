"""Авторизація: BOLA, масове присвоєння, BFLA, scopes, надмірні дані, два входи (API і бот).

python authz_demo.py — секрет JWT генерується тут; лише TestClient.
"""
import secrets

from fastapi.testclient import TestClient

from authz_app import bot_edit_v1, bot_edit_v2, create_app, grant_scopes, issue_token

SECRET = secrets.token_urlsafe(48)


def fresh():
    app = create_app(SECRET)
    users = app.state.users
    tokens = {
        "olena": issue_token(SECRET, users[1], ["notes:read", "notes:write"]),
        "taras": issue_token(SECRET, users[2], ["notes:read", "notes:write"]),
        "taras_ro": issue_token(SECRET, users[2], ["notes:read"]),
        "admin": issue_token(SECRET, users[3], ["notes:read", "notes:write", "users:delete"]),
    }
    return app, TestClient(app), {k: {"Authorization": f"Bearer {v}"} for k, v in tokens.items()}


def title(text: str) -> None:
    print(f"--- {text}")


def show(label: str, response) -> None:
    print(f"   {label:40} → {response.status_code} {response.json()}")


app, api, H = fresh()
title("1. API1 BOLA: чужа нотатка за id")
for version in ("v1", "v2"):
    show(f"Тарас GET /{version}/notes/2 (особиста Олени)", api.get(f"/{version}/notes/2", headers=H["taras"]))
show("Тарас GET /v2/notes/1 (нотатка групи)", api.get("/v2/notes/1", headers=H["taras"]))
show("Тарас GET /v2/notes/999 (немає)", api.get("/v2/notes/999", headers=H["taras"]))

title("2. scopes: токен лише на читання")
r = api.patch("/v2/notes/3", json={"title": "нове"}, headers=H["taras_ro"])
print(f"   {'PATCH з notes:read':40} → {r.status_code} {r.json()} | WWW-Authenticate: {r.headers['www-authenticate']}")
show("GET з notes:read", api.get("/v2/notes/3", headers=H["taras_ro"]))
scheme = app.openapi()["components"]["securitySchemes"]["OAuth2PasswordBearer"]
print("   OpenAPI scopes:", scheme["flows"]["password"]["scopes"])
print("   PATCH /v2/notes/{note_id} security:", app.openapi()["paths"]["/v2/notes/{note_id}"]["patch"]["security"])

title("3. учасник групи бачить, але не змінює")
show("Тарас PATCH /v2/notes/1", api.patch("/v2/notes/1", json={"title": "Зламано"}, headers=H["taras"]))
show("Олена PATCH /v2/notes/1", api.patch("/v2/notes/1", json={"title": "Wi-Fi (новий)"}, headers=H["olena"]))

title("4. API3 масове присвоєння: owner_id у тілі")
show("Тарас PATCH /v1/notes/3 + owner_id=1", api.patch("/v1/notes/3", json={"title": "x", "owner_id": 1},
                                                        headers=H["taras"]))
print("   власник нотатки 3 тепер:", app.state.notes[3].owner_id, "| Тарас її більше не змінить:",
      api.patch("/v1/notes/3", json={"title": "y"}, headers=H["taras"]).status_code)
app, api, H = fresh()
r = api.patch("/v2/notes/3", json={"title": "x", "owner_id": 1}, headers=H["taras"])
print(f"   {'Тарас PATCH /v2/notes/3 + owner_id=1':40} → {r.status_code} {r.json()['detail'][0]['type']} {r.json()['detail'][0]['loc']}")

title("5. API3 надмірні дані у відповіді")
show("GET /v1/users/me", api.get("/v1/users/me", headers=H["taras"]))
show("GET /v2/users/me", api.get("/v2/users/me", headers=H["taras"]))

title("6. API5 BFLA: адмін-функція звичайному користувачу")
print("   /v1/users/{id} в OpenAPI:", "/v1/users/{user_id}" in app.openapi()["paths"])
show("Тарас DELETE /v1/users/1", api.delete("/v1/users/1", headers=H["taras"]))
app, api, H = fresh()
show("Тарас DELETE /v2/users/1", api.delete("/v2/users/1", headers=H["taras"]))
show("адмін DELETE /v2/users/2", api.delete("/v2/users/2", headers=H["admin"]))

title("7. scopes з форми входу: просить клієнт, дає сервер")
app, api, H = fresh()
taras = app.state.users[2]
requested = ["notes:read", "users:delete"]                       # form_data.scopes — те, що надіслав клієнт
as_requested = {"Authorization": f"Bearer {issue_token(SECRET, taras, requested)}"}
show("токен = запитані scopes; DELETE /v2/users/1", api.delete("/v2/users/1", headers=as_requested))
print("   grant_scopes(taras, ...):", grant_scopes(taras, requested))
app, api, H = fresh()
granted = {"Authorization": f"Bearer {issue_token(SECRET, taras, grant_scopes(taras, requested))}"}
show("токен = grant_scopes; DELETE /v2/users/1", api.delete("/v2/users/1", headers=granted))

title("8. два входи: API і бот")
app, api, H = fresh()
print("   API: Тарас PATCH /v2/notes/1 →", api.patch("/v2/notes/1", json={"title": "Зламано"}, headers=H["taras"]).status_code)
print("   бот v1: Тарас /edit 1 →", bot_edit_v1(app, 1002, 1, "Зламано через бота"))
app, api, H = fresh()
print("   бот v2: Тарас /edit 1 →", bot_edit_v2(app, 1002, 1, "Зламано через бота"))
print("   бот v2: Тарас /edit 2 →", bot_edit_v2(app, 1002, 2, "x"))
print("   бот v2: Олена /edit 1 →", bot_edit_v2(app, 1001, 1, "Wi-Fi (з бота)"))
