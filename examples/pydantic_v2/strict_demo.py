"""Режими lax і strict: що Pydantic перетворює сам, як це вимкнути і що ламає strict у FastAPI.

    python strict_demo.py
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, Strict, StrictBool, TypeAdapter, ValidationError


def check(tp: object, value: object, *, strict: bool | None = None, json: bool = False) -> str:
    adapter = TypeAdapter(tp)
    try:
        result = adapter.validate_json(value, strict=strict) if json else adapter.validate_python(value, strict=strict)
        return f"{result!r}"
    except ValidationError as exc:
        return "✗ " + exc.errors()[0]["type"]


print("--- 1. lax: що Pydantic перетворює сам (validate_python)")
cases = [
    (int, "5"), (int, " 5 "), (int, 5.0), (int, 5.5), (int, True), (int, "5.0"),
    (float, "1.5"), (float, 3), (str, 123), (str, b"cheese"),
    (bool, "true"), (bool, "yes"), (bool, "on"), (bool, "1"), (bool, 1), (bool, 2), (bool, "так"),
    (date, "2026-12-01"), (datetime, 1_700_000_000), (UUID, "6f1c0a2e-8f4b-4e7e-9a77-2a1f3c4d5e6f"),
    (Decimal, 0.1), (list[int], ("1", 2)),
]
for tp, value in cases:
    name = getattr(tp, "__name__", str(tp))
    print(f"   {name:9} ← {value!r:42} lax: {check(tp, value):34} strict: {check(tp, value, strict=True)}")

print("--- 2. strict у Python і в JSON: рядок дати")
for tp, raw in ((date, '"2026-12-01"'), (UUID, '"6f1c0a2e-8f4b-4e7e-9a77-2a1f3c4d5e6f"'), (Decimal, '"0.10"'), (int, '"5"')):
    print(f"   {tp.__name__:8} validate_python(strict) {check(tp, raw.strip(chr(34)), strict=True):22}"
          f" validate_json(strict) {check(tp, raw, strict=True, json=True)}")


print("--- 3. чотири способи увімкнути strict і що сильніше")
class Account(BaseModel):
    number: int = Field(strict=True)              # 1. поле
    pin: Annotated[int, Strict()]                 # 2. Annotated + Strict() (або StrictInt)
    balance: float                                # lax


class StrictAccount(BaseModel):
    model_config = ConfigDict(strict=True)        # 3. уся модель
    number: int
    balance: float = Field(strict=False)          # виняток для одного поля


def attempt(title: str, action) -> None:
    try:
        print(f"   {title:52} {action()!r}")
    except ValidationError as exc:
        print(f"   {title:52} ✗ {[(e['loc'][0], e['type']) for e in exc.errors()]}")


data = {"number": "42", "pin": "1234", "balance": "10.5"}
attempt("Account (Field strict + Strict())", lambda: Account.model_validate(data))
attempt("StrictAccount (ConfigDict strict, balance lax)", lambda: StrictAccount.model_validate(data))
attempt("StrictAccount, number=42", lambda: StrictAccount.model_validate({**data, "number": 42}))
attempt("StrictAccount.model_validate(..., strict=False)",            # 4. параметр виклику
        lambda: StrictAccount.model_validate(data, strict=False))
attempt("Account.model_validate(..., strict=False)", lambda: Account.model_validate(data, strict=False))
attempt("Account.model_validate(number=42, pin=1234, strict=True)",
        lambda: Account.model_validate({**data, "number": 42, "pin": 1234}, strict=True))


print("--- 4. strict у FastAPI")
class Booking(BaseModel):
    model_config = ConfigDict(strict=True)
    guests: int
    start: date
    vip: StrictBool = False


app = FastAPI()


@app.post("/bookings")
def book(booking: Booking) -> Booking:
    return booking


@app.get("/rooms")
def rooms(floor: Annotated[int, Query(strict=True)] = 1) -> dict[str, int]:
    return {"floor": floor}


client = TestClient(app)
for title, body in (("JSON-число і дата-рядок", {"guests": 2, "start": "2026-12-01"}),
                    ('guests: "2"', {"guests": "2", "start": "2026-12-01"}),
                    ("vip: 1", {"guests": 2, "start": "2026-12-01", "vip": 1})):
    response = client.post("/bookings", json=body)
    detail = response.json() if response.status_code == 200 else [(e["loc"][-1], e["type"]) for e in response.json()["detail"]]
    print(f"   POST /bookings {title:26} → {response.status_code} {detail}")
response = client.get("/rooms", params={"floor": "3"})
print(f"   GET /rooms?floor=3 (Query strict=True)   → {response.status_code} "
      f"{[(e['loc'][-1], e['type']) for e in response.json()['detail']] if response.status_code != 200 else response.json()}")
