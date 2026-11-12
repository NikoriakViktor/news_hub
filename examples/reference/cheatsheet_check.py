"""Перевірка шпаргалок «Довідника»: кожен фрагмент зі сторінок запускається тут через TestClient.

    pip install -r requirements.txt
    python cheatsheet_check.py

Розділи виводу відповідають розділам сторінок «Шпаргалка FastAPI» і «Шпаргалка Pydantic».
"""
import asyncio
import os
import warnings
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import (APIRouter, BackgroundTasks, Body, Cookie, Depends, FastAPI, File, Form, Header, HTTPException,
                     Path, Query, Request, Response, UploadFile, status)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import (AfterValidator, BaseModel, ConfigDict, Field, SecretStr, TypeAdapter, ValidationError,
                      computed_field, field_serializer, field_validator, model_validator)
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException


def section(title: str) -> None:
    print(f"\n== {title}")


def show(label: str, response: httpx.Response) -> None:
    body = response.json() if response.content and "json" in response.headers.get("content-type", "") else response.text
    print(f"{label:34} → {response.status_code} {body}")


# ---------------------------------------------------------------------------
# FastAPI: lifespan, параметри, відповіді
# ---------------------------------------------------------------------------

EVENTS: list[str] = []


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.store = {"1": "перша новина"}      # ресурс на весь час роботи сервера
    EVENTS.append("startup")
    yield
    EVENTS.append("shutdown")                    # закрити пул, клієнта, з'єднання


app = FastAPI(title="cheatsheet", lifespan=lifespan)


class NewsIn(BaseModel):
    title: str = Field(min_length=10, max_length=300)
    category: str = "Новини"


class NewsOut(NewsIn):
    id: int


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid")      # невідомий параметр рядка запиту → 422
    lang: Literal["uk", "ru"] = "uk"
    limit: int = Field(20, ge=1, le=100)


@app.get("/items/{item_id}")
def read_item(
    item_id: Annotated[int, Path(ge=1)],
    q: Annotated[str | None, Query(max_length=50)] = None,
    tags: Annotated[list[str], Query()] = [],
    x_token: Annotated[str | None, Header()] = None,          # заголовок X-Token
    session: Annotated[str | None, Cookie()] = None,
) -> dict[str, object]:
    return {"item_id": item_id, "q": q, "tags": tags, "x_token": x_token, "session": session}


@app.get("/news")
def list_news(filters: Annotated[Filters, Query()]) -> Filters:
    return filters


@app.post("/news", status_code=status.HTTP_201_CREATED, response_model=NewsOut)
def create_news(body: NewsIn) -> dict[str, object]:
    return {"id": 1, **body.model_dump(), "secret": "не потрапить у відповідь"}


@app.post("/rate")
def rate(score: Annotated[int, Body(embed=True, ge=1, le=5)]) -> dict[str, int]:
    return {"score": score}


@app.post("/login-form")
def login_form(username: Annotated[str, Form()], password: Annotated[str, Form()]) -> dict[str, str]:
    return {"username": username}


@app.post("/upload")
async def upload(file: Annotated[UploadFile, File()]) -> dict[str, object]:
    return {"filename": file.filename, "size": len(await file.read())}


@app.get("/news/{news_id}")
def get_news(news_id: int, request: Request) -> dict[str, str]:
    store: dict[str, str] = request.app.state.store
    if str(news_id) not in store:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"новини {news_id} немає")
    return {"title": store[str(news_id)]}


@app.delete("/news/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_news(news_id: int) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/headers")
def with_headers(response: Response) -> dict[str, bool]:
    response.headers["X-Cache"] = "MISS"
    return {"ok": True}


# ---------------------------------------------------------------------------
# Depends: звичайна, yield, scope="function", кеш на запит
# ---------------------------------------------------------------------------

CALLS: list[str] = []


def pagination(skip: int = 0, limit: int = Query(20, le=100)) -> dict[str, int]:
    CALLS.append("pagination")
    return {"skip": skip, "limit": limit}


def get_db() -> Iterator[str]:
    CALLS.append("db: open")
    try:
        yield "session"
    finally:
        CALLS.append("db: close")


Page = Annotated[dict[str, int], Depends(pagination)]
Db = Annotated[str, Depends(get_db, scope="function")]       # прибирання ДО відповіді


def verify_token(x_token: Annotated[str, Header()]) -> None:
    if x_token != "secret":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="недійсний токен",
                            headers={"WWW-Authenticate": "Bearer"})


@app.get("/deps")
def deps(page: Page, again: Page, db: Db) -> dict[str, object]:
    return {"page": page, "same_object": page is again, "db": db}


# ---------------------------------------------------------------------------
# APIRouter, middleware, exception handlers, BackgroundTasks
# ---------------------------------------------------------------------------

admin = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_token)])


@admin.get("/stats")
def admin_stats() -> dict[str, int]:
    return {"total": 1}


app.include_router(admin)

ORDER: list[str] = []


@app.middleware("http")
async def inner(request: Request, call_next):  # type: ignore[no-untyped-def]
    ORDER.append("inner ←")
    response = await call_next(request)
    ORDER.append("inner →")
    return response


@app.middleware("http")
async def outer(request: Request, call_next):  # type: ignore[no-untyped-def]
    ORDER.append("outer ←")                     # зареєстрований останнім — зовнішній
    response = await call_next(request)
    response.headers["X-Process"] = "ok"
    ORDER.append("outer →")
    return response


class LLMError(Exception):
    pass


@app.exception_handler(LLMError)
async def llm_error(request: Request, error: LLMError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"провайдер недоступний: {error}"})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    fields = [".".join(str(part) for part in e["loc"]) for e in error.errors()]
    return JSONResponse(status_code=422, content={"detail": "неправильні дані", "fields": fields})


@app.exception_handler(StarletteHTTPException)      # і 404/405 маршрутизатора, не лише raise HTTPException
async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"error": error.detail},
                        headers=error.headers)


@app.get("/llm")
def call_llm() -> None:
    raise LLMError("timeout")


SENT: list[str] = []


def notify(title: str) -> None:
    SENT.append(title)


@app.post("/notify", status_code=status.HTTP_202_ACCEPTED)
def start_notify(background: BackgroundTasks) -> dict[str, int]:
    background.add_task(notify, "нова новина")      # після відправлення відповіді
    return {"queued": len(SENT)}


def fastapi_part() -> None:
    section("FastAPI: lifespan і TestClient")
    with TestClient(app) as client:                  # with → lifespan стартує й зупиняється
        print("events після старту:", EVENTS)

        section("FastAPI: параметри")
        show("path + query + header + cookie", client.get(
            "/items/7", params={"q": "ai", "tags": ["a", "b"]}, headers={"X-Token": "t"},
            cookies={"session": "s1"}))
        show("path ge=1", client.get("/items/0"))
        show("query-модель", client.get("/news", params={"lang": "ru", "limit": 5}))
        show("query-модель, extra=forbid", client.get("/news", params={"sort": "date"}))
        show("тіло: модель", client.post("/news", json={"title": "Заголовок новини"}))
        show("тіло: коротке поле", client.post("/news", json={"title": "коротко"}))
        show("Body(embed=True)", client.post("/rate", json={"score": 5}))
        show("Form", client.post("/login-form", data={"username": "admin", "password": "x"}))
        show("File", client.post("/upload", files={"file": ("a.txt", b"hello")}))

        section("FastAPI: відповіді й коди")
        show("HTTPException 404", client.get("/news/99"))
        r = client.delete("/news/1")
        print(f"{'204 без тіла':34} → {r.status_code} {r.content!r}")
        r = client.get("/headers")
        print(f"{'заголовок через Response':34} → {r.status_code} X-Cache={r.headers['X-Cache']}")
        show("невідомий шлях (handler)", client.get("/nope"))
        show("метод не той (handler)", client.put("/headers"))

        section("FastAPI: Depends")
        CALLS.clear()
        show("дві однакові залежності", client.get("/deps"))
        print("виклики:", CALLS)
        show("router без токена", client.get("/admin/stats"))
        show("router з токеном", client.get("/admin/stats", headers={"X-Token": "secret"}))
        app.dependency_overrides[verify_token] = lambda: None
        show("dependency_overrides", client.get("/admin/stats"))
        app.dependency_overrides.clear()

        section("FastAPI: middleware, exception handlers, BackgroundTasks")
        ORDER.clear()
        r = client.get("/headers")
        print("порядок middleware:", ORDER, "| X-Process:", r.headers["X-Process"])
        show("свій виняток → 502", client.get("/llm"))
        show("RequestValidationError", client.get("/items/abc"))
        show("BackgroundTasks", client.post("/notify"))
        print("після відповіді SENT =", SENT)
    print("events після with:", EVENTS)

    section("FastAPI: AsyncClient + ASGITransport")

    async def async_check() -> None:
        async with app.router.lifespan_context(app):         # ASGITransport сам lifespan не запускає
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                show("AsyncClient", await client.get("/news/1"))

    asyncio.run(async_check())

    section("FastAPI: застаріле")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        status.HTTP_422_UNPROCESSABLE_ENTITY  # noqa: B018
        FastAPI().on_event("startup")
    for line in dict.fromkeys(f"{w.category.__name__}: {str(w.message).strip().splitlines()[0]}" for w in caught):
        print(line)
    try:
        APIRouter(prefix="/v1/")
    except AssertionError as error:
        print("APIRouter(prefix='/v1/') → AssertionError:", error)


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------

def strip_title(value: str) -> str:
    return " ".join(value.split())


Title = Annotated[str, AfterValidator(strip_title), Field(min_length=10)]


class News(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Title
    url: str = Field(pattern=r"^https://")
    tags: list[str] = []
    views: int = Field(0, ge=0)
    lang: Literal["uk", "ru"] = Field("uk", validation_alias="language")

    @field_validator("tags")
    @classmethod
    def lower_tags(cls, tags: list[str]) -> list[str]:
        return [tag.lower() for tag in tags]

    @model_validator(mode="after")
    def no_views_for_ru(self) -> "News":
        if self.lang == "ru" and self.views > 0:
            raise ValueError("лічильник лише для uk")
        return self

    @computed_field
    @property
    def domain(self) -> str:
        return self.url.split("/")[2]

    @field_serializer("tags")
    def tags_as_string(self, tags: list[str]) -> str:
        return ",".join(tags)


class Row:                                          # як рядок SQLAlchemy
    def __init__(self) -> None:
        self.id, self.title = 1, "Заголовок з бази даних"


class RowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str


class Patch(BaseModel):
    title: str | None = None
    views: int | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWS_", extra="ignore")
    database_url: str = "sqlite+aiosqlite:///news_hub.db"
    jwt_secret: SecretStr


def pydantic_part() -> None:
    section("Pydantic: модель, валідатори, серіалізація")
    item = News.model_validate({"title": "  Новина   про   ШІ  ", "url": "https://rbc.ua/news/1",
                                "tags": ["AI", "Tech"], "language": "uk"})
    print("model_dump()            →", item.model_dump())
    print("model_dump_json()       →", item.model_dump_json())
    print("exclude/include         →", item.model_dump(include={"title", "lang"}))
    for label, data in [("extra=forbid", {"title": "Новина про ШІ", "url": "https://a.ua", "admin": True}),
                        ("pattern + ge", {"title": "Новина про ШІ", "url": "http://a.ua", "views": -1}),
                        ("model_validator", {"title": "Новина про ШІ", "url": "https://a.ua", "views": 3,
                                             "language": "ru"})]:
        try:
            News.model_validate(data)
        except ValidationError as error:
            print(f"{label:23} →", [(e["type"], e["loc"]) for e in error.errors()])

    section("Pydantic: from_attributes, exclude_unset, TypeAdapter")
    print("from_attributes         →", RowOut.model_validate(Row()))
    print("PATCH exclude_unset     →", Patch.model_validate({"title": "Новий"}).model_dump(exclude_unset=True))
    print("TypeAdapter(list[int])  →", TypeAdapter(list[int]).validate_python(["1", 2]))
    print("JSON Schema (поля)      →", sorted(News.model_json_schema()["properties"]))

    section("Pydantic: settings")
    os.environ["NEWS_JWT_SECRET"] = "x" * 32                       # як export NEWS_JWT_SECRET=…
    settings = Settings()  # type: ignore[call-arg]
    print("database_url            →", settings.database_url)
    print("jwt_secret              →", settings.jwt_secret, "| get_secret_value:",
          len(settings.jwt_secret.get_secret_value()), "символи")


if __name__ == "__main__":
    fastapi_part()
    pydantic_part()
