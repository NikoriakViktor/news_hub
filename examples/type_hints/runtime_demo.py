"""Що з анотацій працює в рантаймі: запити до runtime_app.py, схема OpenAPI і кілька окремих перевірок."""
import json
import warnings
from typing import Annotated, Protocol

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from runtime_app import app

client = TestClient(app)


def show(title: str, response) -> None:
    body = response.json()
    if response.status_code == 422:
        body = [(e["type"], e["loc"], e["msg"]) for e in body["detail"]]
    print(f"--- {title} → {response.status_code}\n   {json.dumps(body, ensure_ascii=False)}")


task = {"title": "Deploy", "status": "todo", "due": None, "tags": ["ops"]}
show("POST /tasks", client.post("/tasks", json=task))
show("status поза Literal", client.post("/tasks", json={**task, "status": "archived"}))
show("без due (str | None без = None)", client.post("/tasks", json={"title": "Deploy", "status": "todo"}))
show("tags: [1, 2]", client.post("/tasks", json={**task, "tags": [1, 2]}))
show("GET /tasks?status=done&limit=99", client.get("/tasks", params={"status": "done", "limit": 99}))
show("GET /raw (-> list[dict])", client.get("/raw"))
show("POST /points (TypedDict)", client.post("/points", json={"x": 1, "y": "2"}))
show("POST /points без y", client.post("/points", json={"x": 1}))

print("--- OpenAPI")
schemas = client.get("/openapi.json").json()["components"]["schemas"]
for field in ("status", "priority", "due", "tags", "title"):
    print(f"   TaskIn.{field}: {json.dumps(schemas['TaskIn']['properties'][field], ensure_ascii=False)}")
print("   TaskIn.required:", schemas["TaskIn"]["required"])
print("   Point:", json.dumps(schemas["Point"]))


print("--- звичайна функція: анотації не перевіряються")
def double(x: int) -> int:
    return x * 2
print("  ", repr(double("ab")), double.__annotations__)


print("--- bare list")
class Bare(BaseModel):
    items: list
print("  ", Bare(items=[1, "a", None]).items, Bare.model_json_schema()["properties"]["items"])


print("--- Protocol як поле моделі")
class Notifier(Protocol):
    def send(self, text: str) -> None: ...
try:
    class Message(BaseModel):
        notifier: Notifier
except Exception as exc:
    print("  ", type(exc).__name__ + ":", str(exc).splitlines()[0])


print("--- Protocol як тіло запиту")
try:
    bad = FastAPI()
    @bad.post("/send")
    def send(notifier: Notifier) -> None: ...
except Exception as exc:
    print("  ", type(exc).__name__ + ":", str(exc).splitlines()[0])


print("--- Annotated з метаданими на першому місці")
def get_db() -> str:
    return "db"
try:
    broken = FastAPI()
    @broken.get("/x")
    def x(db: Annotated[Depends(get_db), str]) -> str:  # type: ignore[valid-type]
        return db
    print("   оголошення пройшло; запит →", TestClient(broken).get("/x").status_code)
except Exception as exc:
    print("  ", type(exc).__name__ + ":", str(exc).splitlines()[0])
try:
    Annotated[int]  # type: ignore[misc]
except TypeError as exc:
    print("   Annotated[int]:", exc)


print("--- constr у Pydantic 2")
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    from pydantic import constr
    class Old(BaseModel):
        name: constr(min_length=3)
print("   попереджень:", [str(w.message)[:80] for w in caught])
try:
    Old(name="ab")
except ValidationError as exc:
    print("   працює:", exc.errors()[0]["type"])
