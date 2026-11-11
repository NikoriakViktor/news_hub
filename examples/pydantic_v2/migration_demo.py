"""Той самий код на Pydantic 1 і Pydantic 2: що змінилося для того, хто мігрує.

    pip install "pydantic<2" && python migration_demo.py
    pip install "pydantic>=2" && python migration_demo.py
"""
import warnings
from typing import Optional

import pydantic
from pydantic import BaseModel, ValidationError

V2 = pydantic.VERSION.startswith("2")
print(f"=== Pydantic {pydantic.VERSION}")


def attempt(title: str, action) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            result = repr(action())
        except ValidationError as exc:
            result = "ValidationError: " + "; ".join(str(e["type"]) for e in exc.errors())
        except Exception as exc:
            result = f"{type(exc).__name__}: {str(exc).splitlines()[0][:90]}"
    note = f"  ⚠ {caught[0].category.__name__}" if caught else ""
    print(f"   {title:34} {result[:90]}{note}")


class Item(BaseModel):
    name: str
    qty: int
    note: Optional[str]                  # без значення за замовчуванням


print("--- перетворення типів")
attempt("name=123 (int → str)", lambda: Item(name=123, qty=1, note=None).name)
attempt("qty='5' (str → int)", lambda: Item(name="a", qty="5", note=None).qty)
attempt("qty=1.5 (float → int)", lambda: Item(name="a", qty=1.5, note=None).qty)
attempt("qty=True (bool → int)", lambda: Item(name="a", qty=True, note=None).qty)
attempt("Optional[str] без note", lambda: Item(name="a", qty=1))

print("--- старі методи")
item = Item(name="a", qty=1, note=None)
attempt(".dict()", lambda: item.dict())
attempt(".json()", lambda: item.json())
attempt(".parse_obj({...})", lambda: Item.parse_obj({"name": "a", "qty": 1, "note": None}))
attempt(".copy(update=...)", lambda: item.copy(update={"qty": 2}).qty)
attempt(".schema()['required']", lambda: Item.schema()["required"])
if V2:
    attempt(".model_dump()", lambda: item.model_dump())
    attempt(".model_copy(update=...)", lambda: item.model_copy(update={"qty": "2"}).qty)


class Row:
    name, qty, note = "a", 1, None


print("--- class Config: orm_mode")
def orm_mode():
    class Out(BaseModel):
        name: str

        class Config:
            orm_mode = True
    return Out.from_orm(Row())
attempt("Config.orm_mode + from_orm()", orm_mode)


print("--- @validator")
def old_validator():
    from pydantic import validator

    class Named(BaseModel):
        name: str

        @validator("name")
        def strip(cls, value):
            return value.strip()
    return Named(name="  a ").name
attempt("@validator", old_validator)


class User(BaseModel):
    name: str


class Admin(User):
    password_hash: str


class Team(BaseModel):
    owner: User


print("--- підклас у полі базового типу")
attempt("Team(owner=Admin(...)).dict()", lambda: Team(owner=Admin(name="o", password_hash="h")).dict())
