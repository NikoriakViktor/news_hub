"""Три способи версіонувати API на тих самих даних: шлях (/api/v1, /api/v2), заголовок, параметр.

    uvicorn versioning_app:app --reload        # /docs — обидві версії поруч
    python versioning_demo.py
"""
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel

USERS = {1: {"id": 1, "first_name": "Олена", "last_name": "Коваленко"}}   # одне сховище для всіх версій


class UserV1(BaseModel):          # старий контракт: одне поле з повним ім'ям
    id: int
    full_name: str


class UserV2(BaseModel):          # новий контракт: ім'я й прізвище окремо
    id: int
    first_name: str
    last_name: str


def load(user_id: int) -> dict:
    if user_id not in USERS:
        raise HTTPException(404, "User not found")
    return USERS[user_id]


def to_v1(user: dict) -> UserV1:
    return UserV1(id=user["id"], full_name=f"{user['first_name']} {user['last_name']}")


# --- 1. Версія в шляху: окремий роутер на версію --------------------------------------------
v1 = APIRouter(prefix="/v1", tags=["v1"], deprecated=True)     # deprecated → позначка в OpenAPI і /docs
v2 = APIRouter(prefix="/v2", tags=["v2"])


@v1.get("/users/{user_id}")
def get_user_v1(user_id: int, response: Response) -> UserV1:
    response.headers["Deprecation"] = "@1793491200"     # RFC 9745: застаріла з 2026-11-01 (unix-час)
    response.headers["Sunset"] = "Thu, 01 Jul 2027 00:00:00 GMT"   # RFC 8594: коли її вимкнуть
    response.headers["Link"] = f'</api/v2/users/{user_id}>; rel="successor-version"'
    return to_v1(load(user_id))


@v2.get("/users/{user_id}")
def get_user_v2(user_id: int) -> UserV2:
    return UserV2(**load(user_id))


api = APIRouter(prefix="/api")
api.include_router(v1)
api.include_router(v2)
app = FastAPI(title="Versioning")
app.include_router(api)


# --- 2. Версія в заголовку: одна адреса, відповідь залежить від заголовка -------------------
@app.get("/users/{user_id}", tags=["header"])
def get_user_by_header(
    user_id: int,
    response: Response,
    x_api_version: Annotated[Literal["1", "2"], Header()] = "2",
) -> UserV1 | UserV2:
    response.headers["Vary"] = "X-API-Version"          # кеш мусить розрізняти відповіді за цим заголовком
    user = load(user_id)
    return to_v1(user) if x_api_version == "1" else UserV2(**user)


# --- 3. Версія в параметрі запиту ------------------------------------------------------------
@app.get("/q/users/{user_id}", tags=["query"])
def get_user_by_query(user_id: int, version: Annotated[Literal["1", "2"], Query()] = "2") -> UserV1 | UserV2:
    user = load(user_id)
    return to_v1(user) if version == "1" else UserV2(**user)
