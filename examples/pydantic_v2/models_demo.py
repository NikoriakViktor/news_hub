"""Pydantic 2: Field, model_validate, model_dump(mode=...), exclude_unset — що відбувається насправді.

    python models_demo.py
"""
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SerializeAsAny, ValidationError, field_validator


def errors(exc: ValidationError) -> list[tuple[str, tuple, object]]:
    return [(e["type"], e["loc"], e["input"]) for e in exc.errors()]


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    sku: str = Field(pattern=r"^[A-Z]{3}-\d{4}$")
    tags: list[str] = Field(default_factory=list, max_length=5)


print("--- 1. Field: обмеження")
try:
    ProductCreate.model_validate({"name": "А", "price": -10, "sku": "bad_sku", "tags": ["a"] * 6})
except ValidationError as exc:
    for item in errors(exc):
        print("  ", item)


class Product(BaseModel):
    id: UUID
    name: str
    price: Decimal
    created_at: datetime
    site: HttpUrl
    tags: set[str] = set()


product = Product.model_validate({
    "id": "6f1c0a2e-8f4b-4e7e-9a77-2a1f3c4d5e6f", "name": "Ноутбук", "price": "25000.50",
    "created_at": "2026-11-11T12:05:00+00:00", "site": "https://shop.example", "tags": ["sale"],
})

print("--- 2. model_dump(): mode='python' проти mode='json'")
python_dump, json_dump = product.model_dump(), product.model_dump(mode="json")
for key in python_dump:
    print(f"   {key:10} {type(python_dump[key]).__name__:9} → {json_dump[key]!r}")
try:
    json.dumps(python_dump)
except TypeError as exc:
    print("   json.dumps(model_dump()):", exc)
print("   model_dump_json():", product.model_dump_json()[:80], "...")


@dataclass
class Row:                      # замість рядка з бази: об'єкт з атрибутами, не словник
    id: int
    name: str
    password_hash: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class UserOutNoAttrs(BaseModel):
    id: int
    name: str


print("--- 3. model_validate з об'єкта")
row = Row(1, "olena", "$2b$12$...")
print("   from_attributes=True:", UserOut.model_validate(row))
try:
    UserOutNoAttrs.model_validate(row)
except ValidationError as exc:
    print("   без from_attributes:", errors(exc)[0][0])


class NewsPatch(BaseModel):
    title: str | None = Field(None, min_length=10)
    category: str | None = None
    pinned: bool = False


print("--- 4. exclude_unset, exclude_defaults, exclude_none")
for body in ({"category": "Спорт"}, {"title": None}, {"pinned": False}):
    patch = NewsPatch.model_validate(body)
    print(f"   тіло {json.dumps(body, ensure_ascii=False):22} model_dump()={patch.model_dump()}")
    print(f"   {'':27} exclude_unset={patch.model_dump(exclude_unset=True)}  "
          f"exclude_defaults={patch.model_dump(exclude_defaults=True)}  "
          f"exclude_none={patch.model_dump(exclude_none=True)}  fields_set={patch.model_fields_set}")


class NewsPatchSafe(BaseModel):
    title: str | None = Field(None, min_length=10)
    category: str | None = None

    @field_validator("title", "category")
    @classmethod
    def not_null(cls, value: str | None) -> str:
        if value is None:                 # валідатор не бачить значення за замовчуванням — лише передане
            raise ValueError("поле можна не передавати, але не можна передати null")
        return value


print("--- 4b. явний null у PATCH")
print("   без тіла:", NewsPatchSafe.model_validate({}).model_dump(exclude_unset=True))
try:
    NewsPatchSafe.model_validate({"title": None})
except ValidationError as exc:
    print("   {'title': None}:", errors(exc), exc.errors()[0]["msg"])


class User(BaseModel):
    name: str


class Admin(User):
    password_hash: str


class Team(BaseModel):
    owner: User
    any_owner: SerializeAsAny[User]


print("--- 5. підклас у полі базового типу")
admin = Admin(name="olena", password_hash="$2b$12$...")
print("  ", Team(owner=admin, any_owner=admin).model_dump())


class Account(BaseModel):
    name: str
    password_hash: str = Field(exclude=True)


print("--- 6. Field(exclude=True)")
print("  ", Account(name="olena", password_hash="$2b$12$...").model_dump())
