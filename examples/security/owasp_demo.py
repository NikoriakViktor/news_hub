"""OWASP API Security Top 10 (2023): пункти, яких не показують інші приклади цієї папки.

python owasp_demo.py — лише TestClient; секрет JWT генерується тут.

- API4 Unrestricted Resource Consumption — межі параметрів і тіла запиту;
- API8 Security Misconfiguration — debug=True і текст винятку у відповіді;
- API9 Improper Inventory Management — маршрути, яких не видно в /docs, і маршрути без перевірки;
- API10 Unsafe Consumption of APIs — відповідь чужого API як недовірений вхід.
"""
import secrets
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, ValidationError

from authz_app import create_app


def title(text: str) -> None:
    print(f"--- {text}")


ROWS = list(range(1_000_000))
app = FastAPI()


@app.get("/v1/items")
def items_v1(limit: int = 20) -> dict[str, int]:
    return {"returned": len(ROWS[:limit])}


@app.get("/v2/items")
def items_v2(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> dict[str, int]:
    return {"returned": len(ROWS[:limit])}


class Tags(BaseModel):
    tags: list[Annotated[str, Field(max_length=30)]] = Field(max_length=10)


@app.post("/v2/tags")
def tags(body: Tags) -> dict[str, int]:
    return {"tags": len(body.tags)}


api = TestClient(app)
title("1. API4: межі параметрів і тіла")
print("   GET /v1/items?limit=1000000 →", api.get("/v1/items", params={"limit": 1_000_000}).json())
r = api.get("/v2/items", params={"limit": 1_000_000})
print("   GET /v2/items?limit=1000000 →", r.status_code, r.json()["detail"][0]["type"], r.json()["detail"][0]["ctx"])
r = api.post("/v2/tags", json={"tags": ["x"] * 10_000})
print("   POST /v2/tags, 10 000 тегів →", r.status_code, r.json()["detail"][0]["type"], r.json()["detail"][0]["loc"])

# ---------------------------------------------------------------------------
title("2. API8: debug=True і текст винятку")
for debug in (True, False):
    broken = FastAPI(debug=debug)

    @broken.get("/boom")
    def boom() -> None:
        raise RuntimeError("connection to postgresql://news:S3cr3t@db:5432/news failed")

    r = TestClient(broken, raise_server_exceptions=False).get("/boom")
    print(f"   debug={debug!s:5} → {r.status_code} {r.headers['content-type'].split(';')[0]:10} "
          f"пароль у відповіді: {'S3cr3t' in r.text} | {r.text.splitlines()[0]!r}")

leaky = FastAPI()


@leaky.get("/leaky")
def leaky_route() -> None:
    try:
        raise RuntimeError("connection to postgresql://news:S3cr3t@db:5432/news failed")
    except RuntimeError as error:
        raise HTTPException(503, detail=str(error)) from error                 # «зручно для налагодження»


print("   HTTPException(detail=str(error)) →", TestClient(leaky).get("/leaky").json())

# ---------------------------------------------------------------------------
title("3. API9: інвентар маршрутів")
notes_app = create_app(secrets.token_urlsafe(48))
documented = set()
for path, operations in notes_app.openapi()["paths"].items():
    documented |= {(method.upper(), path) for method in operations}


def protected(route: APIRoute) -> bool:
    stack = list(route.dependant.dependencies)
    while stack:
        dependency = stack.pop()
        if getattr(dependency.call, "__name__", "") == "current_user":         # у News Hub: `is require_admin`
            return True
        stack.extend(dependency.dependencies)
    return False


for route in notes_app.routes:
    if not isinstance(route, APIRoute):
        continue
    for method in sorted(route.methods):
        flags = [] if (method, route.path) in documented else ["немає в /docs"]
        flags += [] if protected(route) else ["без перевірки"]
        if route.path.startswith("/v1"):
            flags.append("стара версія")
        print(f"   {method:6} {route.path:22} {', '.join(flags) or 'ok'}")
print("   службові маршрути (не APIRoute):", sorted(r.path for r in notes_app.routes if not isinstance(r, APIRoute)))

# ---------------------------------------------------------------------------
title("4. API10: відповідь чужого API — недовірений вхід")


class PartnerNews(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=1, max_length=300)
    url: HttpUrl


replies = {
    "звичайна": {"title": "Новина", "url": "https://partner.example/n/1", "debug": "ignored"},
    "javascript: в url": {"title": "Новина", "url": "javascript:alert(document.cookie)"},
    "заголовок 1 МБ": {"title": "x" * 1_000_000, "url": "https://partner.example/n/2"},
    "немає url": {"title": "Новина"},
}
for name, reply in replies.items():
    try:
        item = PartnerNews.model_validate(reply)
        print(f"   {name:18} → прийнято: {item.model_dump(mode='json')}")
    except ValidationError as error:
        print(f"   {name:18} → відхилено: {[(e['type'], e['loc']) for e in error.errors()]}")
