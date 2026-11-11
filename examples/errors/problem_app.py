"""Помилки у форматі RFC 9457 (application/problem+json) замість стандартного {"detail": ...} FastAPI.

    python problem_demo.py
"""
import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("problem_app")
PROBLEM = "application/problem+json"


class InvalidParam(BaseModel):
    name: str          # "body.password", "query.limit"
    reason: str        # повідомлення Pydantic
    code: str          # тип помилки Pydantic: string_too_short, missing, …


class Problem(BaseModel):
    """RFC 9457: type, title, status, detail, instance + розширення."""
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    invalid_params: list[InvalidParam] | None = None


def problem(status: int, request: Request, *, detail: str | None = None, type_: str = "about:blank",
            title: str | None = None, headers: dict[str, str] | None = None, **ext: Any) -> JSONResponse:
    body = Problem(type=type_, title=title or HTTPStatus(status).phrase, status=status,
                   detail=detail, instance=request.url.path, **ext)
    return JSONResponse(body.model_dump(exclude_none=True), status_code=status,
                        media_type=PROBLEM, headers=headers)


app = FastAPI(
    title="Problem Details",
    # опис 422 у /docs теж замінюємо, інакше OpenAPI обіцяє старий формат HTTPValidationError
    # model реєструє схему Problem у components; FastAPI кладе її під application/json, тож явно додаємо й problem+json
    responses={422: {"model": Problem, "description": "Помилка перевірки",
                     "content": {PROBLEM: {"schema": {"$ref": "#/components/schemas/Problem"}}}}},
)


@app.exception_handler(StarletteHTTPException)          # базовий клас: ловить і наші 404, і 404/405 маршрутизатора
async def http_problem(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail != HTTPStatus(exc.status_code).phrase else None
    return problem(exc.status_code, request, detail=detail, headers=exc.headers)   # headers: WWW-Authenticate тощо


@app.exception_handler(RequestValidationError)
async def validation_problem(request: Request, exc: RequestValidationError) -> JSONResponse:
    params = [InvalidParam(name=".".join(str(part) for part in error["loc"]), reason=error["msg"], code=error["type"])
              for error in exc.errors()]                 # лише loc, msg, type: без input (паролі) і ctx (об'єкти)
    return problem(422, request, type_="/problems/validation-error", title="Запит не пройшов перевірку",
                   detail=f"Помилок: {len(params)}", invalid_params=[p.model_dump() for p in params])


@app.exception_handler(Exception)
async def server_problem(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s", request.url.path)                   # подробиці — у журнал
    return problem(500, request)                                               # клієнту — без подробиць


class Signup(BaseModel):
    email: str
    password: str = Field(min_length=12)

    @field_validator("email")
    @classmethod
    def has_at(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("email без @")
        return value


@app.post("/signup", status_code=201)
def signup(body: Signup) -> dict:
    return {"email": body.email}


@app.get("/items/{item_id}")
def item(item_id: int) -> dict:
    raise HTTPException(404, f"Item {item_id} not found")


@app.get("/private")
def private() -> dict:
    raise HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})


@app.get("/boom")
def boom() -> dict:
    raise RuntimeError("password=secret host=db.internal")
