"""field_validator, model_validator, computed_field: коли що, порядок, помилки.

    python validators_demo.py
"""
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import (BaseModel, Field, ValidationInfo, ValidationError, computed_field, field_validator,
                      model_validator)


def errors(exc: ValidationError) -> list[tuple[str, tuple, str]]:
    return [(e["type"], e["loc"], e["msg"]) for e in exc.errors()]


def attempt(title: str, action) -> None:
    try:
        print(f"   {title:40} {action()!r}")
    except ValidationError as exc:
        print(f"   {title:40} ValidationError {errors(exc)}")
    except Exception as exc:
        print(f"   {title:40} {type(exc).__name__}: {exc}  ← не ValidationError")


class Booking(BaseModel):
    promo_code: str
    base_price: Decimal = Field(gt=0)
    discount: Decimal = Field(default=Decimal(0), ge=0)
    start: date
    end: date

    @field_validator("promo_code", mode="before")      # сире значення: може бути будь-чим
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("promo_code")                      # mode="after": уже str
    @classmethod
    def known_format(cls, value: str) -> str:
        if not value.isalnum() or len(value) < 3:
            raise ValueError("промокод: щонайменше 3 літери чи цифри")
        return value

    @model_validator(mode="after")                     # усі поля вже перевірені
    def dates_and_discount(self) -> "Booking":
        if self.start >= self.end:
            raise ValueError("start має бути раніше за end")
        if self.discount > self.base_price:
            raise ValueError("знижка більша за ціну")
        return self

    @computed_field                                    # не приймається на вході, з'являється на виході
    @property
    def final_price(self) -> Decimal:
        return self.base_price - self.discount


ok = {"promo_code": "  sale2026 ", "base_price": "100", "discount": "15", "start": "2026-12-01", "end": "2026-12-10"}

print("--- 1. before → after → model_validator → computed_field")
attempt("правильне бронювання", lambda: Booking.model_validate(ok).model_dump(mode="json"))
attempt("promo_code=123 (before пропустив не-str)", lambda: Booking.model_validate({**ok, "promo_code": 123}))
attempt("promo_code='ab'", lambda: Booking.model_validate({**ok, "promo_code": "ab"}))
attempt("start > end", lambda: Booking.model_validate({**ok, "start": "2026-12-15"}))
attempt("start > end і base_price=-1", lambda: Booking.model_validate({**ok, "start": "2026-12-15", "base_price": -1}))
attempt("final_price у вхідних даних", lambda: Booking.model_validate({**ok, "final_price": 1}).final_price)


print("--- 2. порядок кількох валідаторів одного поля")
class Order(BaseModel):
    code: str

    @field_validator("code", mode="before")
    @classmethod
    def before_1(cls, value: Any) -> Any:
        print("      before_1", repr(value)); return value

    @field_validator("code", mode="before")
    @classmethod
    def before_2(cls, value: Any) -> Any:
        print("      before_2", repr(value)); return value

    @field_validator("code")
    @classmethod
    def after_1(cls, value: str) -> str:
        print("      after_1", repr(value)); return value

    @field_validator("code")
    @classmethod
    def after_2(cls, value: str) -> str:
        print("      after_2", repr(value)); return value

Order(code="x")


print("--- 3. типові помилки")
class NoReturn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def check(cls, value: str) -> str:
        if not value:
            raise ValueError("порожнє ім'я")
        # return value — забули
attempt("валідатор без return", lambda: NoReturn(name="olena").name)


class Unsafe(BaseModel):
    code: str

    @field_validator("code", mode="before")
    @classmethod
    def strip(cls, value: Any) -> Any:
        return value.strip()                           # для int — AttributeError
attempt("before без isinstance, code=5", lambda: Unsafe(code=5))


class WithAssert(BaseModel):
    qty: int

    @field_validator("qty")
    @classmethod
    def positive(cls, value: int) -> int:
        assert value > 0, "кількість має бути додатною"   # python -O видаляє assert
        return value
attempt("assert у валідаторі", lambda: WithAssert(qty=0))


class Period(BaseModel):
    start: date
    end: date

    @field_validator("start")
    @classmethod
    def before_end(cls, value: date, info: ValidationInfo) -> date:
        print("      info.data у валідаторі start:", info.data)
        if value >= info.data["end"]:                  # end оголошено нижче — його ще немає
            raise ValueError("start має бути раніше за end")
        return value
attempt("info.data з полем, оголошеним нижче", lambda: Period(start="2026-12-01", end="2026-12-10"))


print("--- 4. model_validator(mode='before'): вхід може бути не словником")
class Point(BaseModel):
    x: int
    y: int

    @model_validator(mode="before")
    @classmethod
    def from_pair(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)) and len(data) == 2:   # [1, 2] → {"x": 1, "y": 2}
            return {"x": data[0], "y": data[1]}
        return data
attempt("Point.model_validate([1, 2])", lambda: Point.model_validate([1, 2]))
attempt("Point.model_validate({'x': 1, 'y': 2})", lambda: Point.model_validate({"x": 1, "y": 2}))


print("--- 5. у FastAPI")
class Signup(BaseModel):
    email: str
    password: str
    password_repeat: str

    @model_validator(mode="after")
    def passwords_match(self) -> "Signup":
        if self.password != self.password_repeat:
            raise ValueError("паролі не збігаються")
        return self


app = FastAPI()


@app.post("/bookings")
def book(booking: Booking) -> Booking:
    return booking


@app.post("/signup")
def signup(body: Signup) -> dict[str, str]:
    return {"email": body.email}


@app.post("/unsafe")
def unsafe(body: Unsafe) -> Unsafe:
    return body


client = TestClient(app, raise_server_exceptions=False)
print("  ", client.post("/bookings", json=ok).json())
response = client.post("/signup", json={"email": "a@b.c", "password": "hunter2-secret", "password_repeat": "hunter3"})
print("  ", response.status_code, response.json()["detail"][0])
response = client.post("/unsafe", json={"code": 5})
print("   /unsafe code=5 →", response.status_code, response.text)
schemas = client.get("/openapi.json").json()["components"]["schemas"]
print("   OpenAPI:", sorted(name for name in schemas if name.startswith("Booking")))
print("   Booking-Output.final_price:", schemas["Booking-Output"]["properties"]["final_price"],
      "| required:", "final_price" in schemas["Booking-Output"]["required"])
print("   Booking-Input має final_price:", "final_price" in schemas["Booking-Input"]["properties"])
