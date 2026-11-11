"""Що FastAPI відповідає сам: битий JSON, чужий Content-Type, необроблений виняток, 204 з тілом, Bearer без токена.

    uvicorn codes_app:app --port 8016
    curl -i -X POST localhost:8016/items -H "content-type: application/json" -d '{"slug": "abc"'
    curl -i localhost:8016/boom
    curl -i -X DELETE localhost:8016/items/1
    curl -i localhost:8016/private
"""
from typing import Annotated
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

app = FastAPI()
bearer = HTTPBearer()

class Item(BaseModel):
    slug: str = Field(min_length=3)

@app.post("/items", status_code=201)
def create(item: Item) -> Item:
    return item

@app.get("/boom")
def boom() -> dict:
    return {"x": 1 / 0}

@app.delete("/items/{i}", status_code=204)
def delete(i: int):
    return {"deleted": i}           # тіло при 204?

@app.get("/private")
def private(cred: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]) -> dict:
    return {"token": cred.credentials}
