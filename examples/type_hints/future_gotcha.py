"""from __future__ import annotations: анотації стають рядками, і FastAPI мусить знайти Item за назвою.
Клас, оголошений усередині функції, він не знаходить — і мовчки робить item query-параметром.

    python future_gotcha.py
"""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

def make_app() -> FastAPI:
    class Item(BaseModel):
        name: str
    app = FastAPI()
    @app.post("/items")
    def create(item: Item) -> Item:
        return item
    return app

try:
    r = TestClient(make_app()).post("/items", json={"name": "a"})
    print(r.status_code, r.text[:200])
except Exception as e:
    print(type(e).__name__, str(e).splitlines()[0][:200])
