"""ValidationError: з чого складається помилка, як її показати людині і де вона стає 500 замість 422.

    python validation_error_demo.py
"""
import json
from typing import Annotated, Any

from fastapi import FastAPI, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from pydantic_core import PydanticCustomError


class Item(BaseModel):
    sku: str = Field(pattern=r"^[A-Z]{3}-\d{4}$")
    qty: int = Field(ge=1, le=1000)


class Order(BaseModel):
    email: str
    items: list[Item] = Field(min_length=1)
    coupon: str | None = None

    @field_validator("email")
    @classmethod
    def has_at(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("email без @")
        return value

    @field_validator("coupon")
    @classmethod
    def known_coupon(cls, value: str | None) -> str | None:
        if value is not None and value != "SALE":
            raise PydanticCustomError("coupon_unknown", "Купон {coupon} не діє", {"coupon": value})
        return value


bad = {"email": "olena", "items": [{"sku": "ABC-1234", "qty": 5}, {"sku": "bad", "qty": 0}], "coupon": "FREE"}

print("--- 1. exc.errors(): усі ключі")
try:
    Order.model_validate(bad)
except ValidationError as exc:
    print(f"   title={exc.title!r} error_count={exc.error_count()}")
    for error in exc.errors():
        print("  ", error)
    print("--- 2. errors(include_url=False, include_context=False, include_input=False)")
    for error in exc.errors(include_url=False, include_context=False, include_input=False):
        print("  ", error)
    print("--- 3. json.dumps(exc.errors()) і exc.json()")
    try:
        json.dumps(exc.errors())
    except TypeError as error:
        print("   json.dumps:", error)
    print("   exc.json():", exc.json()[:110], "...")

print("--- 4. input — bytes, якщо перевіряли model_validate_json(bytes)")
try:
    Order.model_validate_json(b'{"email": "olena@example.com"')
except ValidationError as exc:
    error = exc.errors()[0]
    print(f"   {error['type']} loc={error['loc']} input={error['input']!r}")


UK = {
    "missing": "Обов'язкове поле",
    "string_too_short": "Щонайменше {min_length} символів",
    "string_pattern_mismatch": "Не відповідає формату",
    "greater_than_equal": "Має бути не менше {ge}",
    "less_than_equal": "Має бути не більше {le}",
    "too_short": "Потрібно щонайменше {min_length} елемент(и)",
    "int_parsing": "Має бути цілим числом",
}


def to_user(errors: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Помилки → {"поле": ["повідомлення українською"]}; без input, без внутрішніх об'єктів."""
    result: dict[str, list[str]] = {}
    for error in errors:
        loc = [str(part) for part in error["loc"] if part not in ("body", "query", "path", "header", "cookie")]
        field = ".".join(loc) or "__all__"
        template = UK.get(error["type"])
        message = template.format(**error.get("ctx", {})) if template else error["msg"].removeprefix("Value error, ")
        result.setdefault(field, []).append(message)
    return result


class Signup(BaseModel):
    email: str
    password: str = Field(min_length=12)
    password_repeat: str

    @model_validator(mode="after")
    def same(self) -> "Signup":
        if self.password != self.password_repeat:
            raise ValueError("паролі не збігаються")
        return self


app = FastAPI()


@app.exception_handler(RequestValidationError)
async def friendly(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse({"errors": to_user(exc.errors())}, status_code=422)


@app.post("/orders")
def create_order(order: Order) -> dict[str, int]:
    return {"items": len(order.items)}


@app.get("/search")
def search(limit: Annotated[int, Query(ge=1, le=50)] = 10,
           x_request_id: Annotated[str | None, Header(min_length=8)] = None) -> dict[str, int]:
    return {"limit": limit}


@app.post("/signup")
def signup(body: Signup) -> dict[str, str]:
    return {"email": body.email}


@app.post("/import")
def import_raw(payload: dict[str, Any]) -> dict[str, int]:
    order = Order.model_validate(payload)         # ValidationError усередині маршруту — не RequestValidationError
    return {"items": len(order.items)}


client = TestClient(app, raise_server_exceptions=False)
print("--- 5. обробник RequestValidationError: повідомлення для людини")
print("   POST /orders →", client.post("/orders", json=bad).json())
print("   GET /search →", client.get("/search", params={"limit": "x"}, headers={"X-Request-ID": "1"}).json())
print("   POST /signup →", client.post("/signup", json={"email": "a@b.c", "password": "hunter2", "password_repeat": "x"}).json())

print("--- 6. ValidationError усередині маршруту")
response = client.post("/import", json=bad)
print(f"   POST /import → {response.status_code} {response.text}")


print("--- 7. стандартний detail FastAPI і model_validator: що в input")
plain = FastAPI()


@plain.post("/signup")
def plain_signup(body: Signup) -> dict[str, str]:
    return {"email": body.email}


detail = TestClient(plain).post("/signup", json={"email": "a@b.c", "password": "correct horse battery", "password_repeat": "x"}).json()["detail"]
print("  ", jsonable_encoder(detail))
