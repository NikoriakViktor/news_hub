"""ConfigDict: extra, frozen, from_attributes — що кожен робить і де ламається.

    python config_demo.py
"""
import asyncio
import json
import warnings

from fastapi import FastAPI
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, selectinload


# побічний ефект невдалого лінивого завантаження в async — не заважає читати вивід
warnings.filterwarnings("ignore", message="coroutine .* was never awaited")


def show(title: str, action) -> None:
    try:
        print(f"   {title:42} {action()}")
    except ValidationError as exc:
        error = exc.errors()[0]
        print(f"   {title:42} ValidationError: {error['type']} {error['loc']} — {error['msg'].splitlines()[0][:95]}")
    except Exception as exc:
        print(f"   {title:42} {type(exc).__name__}: {str(exc).splitlines()[0][:80]}")


# --- 1. extra ---------------------------------------------------------------------------------
class Ignore(BaseModel):
    name: str


class Forbid(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


class Allow(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str


data = {"name": "olena", "is_admin": True}
print("--- 1. extra: що буде з полем, якого немає в моделі")
show('"ignore" (за замовчуванням)', lambda: repr(Ignore.model_validate(data)))
show('"forbid"', lambda: Forbid.model_validate(data))
allowed = Allow.model_validate(data)
show('"allow": модель', lambda: repr(allowed))
show('"allow": model_extra', lambda: allowed.model_extra)
show('"allow": model_dump()', lambda: allowed.model_dump())
show('JSON Schema "forbid"', lambda: json.dumps(Forbid.model_json_schema()))
show('JSON Schema "allow"', lambda: json.dumps(Allow.model_json_schema()))


# --- 2. frozen --------------------------------------------------------------------------------
class Item(BaseModel):
    model_config = ConfigDict(frozen=True)
    url: str
    tags: list[str] = []


class Point(BaseModel):
    model_config = ConfigDict(frozen=True)
    x: int
    y: int


class Account(BaseModel):
    id: int = Field(frozen=True)
    name: str


item = Item(url="https://a.example/1", tags=["uk"])
print("--- 2. frozen")
show("item.url = ...", lambda: setattr(item, "url", "https://b.example"))
show("item.tags.append(...) — вкладене", lambda: (item.tags.append("hacked"), item.tags)[1])
show("model_copy(update=...)", lambda: repr(item.model_copy(update={"url": 42})))
show("hash(Point) і множина", lambda: len({Point(x=1, y=2), Point(x=1, y=2), Point(x=2, y=2)}))
show("hash(Item) — у полі list", lambda: hash(item))
show("Field(frozen=True): account.id = 2", lambda: setattr(Account(id=1, name="a"), "id", 2))
show("Field(frozen=True): account.name = 'b'", lambda: (lambda a: (setattr(a, "name", "b"), a.name)[1])(Account(id=1, name="a")))


# --- 3. validate_assignment -------------------------------------------------------------------
class Loose(BaseModel):
    qty: int


class Checked(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    qty: int


print("--- 3. присвоєння без frozen: перевіряється лише з validate_assignment")
show("Loose: qty = 'багато'", lambda: (lambda m: (setattr(m, "qty", "багато"), repr(m))[1])(Loose(qty=1)))
show("Checked: qty = 'багато'", lambda: setattr(Checked(qty=1), "qty", "багато"))
show("Checked: qty = '5' (lax)", lambda: (lambda m: (setattr(m, "qty", "5"), repr(m))[1])(Checked(qty=1)))


# --- 4. успадкування ConfigDict ---------------------------------------------------------------
class Base(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)
    title: str


class Child(Base):
    model_config = ConfigDict(from_attributes=True)


print("--- 4. успадкування: конфіг дочірнього класу зливається з батьківським")
show("Child.model_config", lambda: Child.model_config)
show("Child(title='  x  ').title = ...", lambda: setattr(Child(title="  x  "), "title", "y"))


# --- 5. from_attributes з ORM -----------------------------------------------------------------
class Db(DeclarativeBase):
    pass


class AuthorRow(Db):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(String(100))
    posts: Mapped[list["PostRow"]] = relationship(back_populates="author")


class PostRow(Db):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"))
    author: Mapped[AuthorRow] = relationship(back_populates="posts")


class AuthorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    author: AuthorOut


class AuthorNoConfig(BaseModel):          # без from_attributes
    id: int
    name: str


class PostNestedNoConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    author: AuthorNoConfig


class AuthorWithPosts(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    posts: list[PostOut]                   # пост → автор → пости → ... лише якщо моделі так описані


engine = create_async_engine("sqlite+aiosqlite://")


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Db.metadata.create_all)
    make = async_sessionmaker(engine, expire_on_commit=False)
    async with make() as session:
        author = AuthorRow(name="olena", password_hash="$2b$12$secret")
        session.add(PostRow(title="перший", author=author))
        await session.commit()

    print("--- 5. from_attributes з SQLAlchemy")
    async with make() as session:
        post = (await session.execute(select(PostRow).options(selectinload(PostRow.author)))).scalar_one()
        show("вкладений author із selectinload", lambda: repr(PostOut.model_validate(post)))
        show("вкладена модель без from_attributes", lambda: PostNestedNoConfig.model_validate(post))
        show("password_hash у результаті?", lambda: "password_hash" in PostOut.model_validate(post).model_dump()["author"])

    print("--- 6. async: ліниве завантаження зв'язку")
    async with make() as session:
        post = (await session.execute(select(PostRow))).scalar_one()
        show("без selectinload → post.author", lambda: PostOut.model_validate(post))
    async with make() as session:
        author = (await session.execute(select(AuthorRow))).scalar_one()
        show("AuthorWithPosts без selectinload", lambda: AuthorWithPosts.model_validate(author))

    print("--- 7. маршрут FastAPI: response_model з від'єднаним об'єктом")
    app = FastAPI()

    @app.get("/posts/1", response_model=PostOut)
    async def get_post() -> PostRow:
        async with make() as s:
            return (await s.execute(select(PostRow))).scalar_one()      # сесія закрилась, author не завантажено

    response = TestClient(app, raise_server_exceptions=False).get("/posts/1")
    print(f"   GET /posts/1 → {response.status_code} {response.text[:60]}")
    try:
        TestClient(app).get("/posts/1")
    except ResponseValidationError as exc:
        error = exc.errors()[0]
        print(f"   {'причина':42} ResponseValidationError: {error['type']} {error['loc']} — {error['msg'][:70]}")
    await engine.dispose()


asyncio.run(main())


# --- 8. масове присвоєння ---------------------------------------------------------------------
class UserRow(Db):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    is_admin: Mapped[bool] = mapped_column(default=False)


class UserCreate(BaseModel):
    name: str


class UserCreateAllow(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str


class UserCreateForbid(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


attack = {"name": "mallory", "is_admin": True}
print("--- 8. масове присвоєння: UserRow(**body.model_dump())")
show("ignore → is_admin", lambda: UserRow(**UserCreate.model_validate(attack).model_dump()).is_admin)
show("allow → is_admin", lambda: UserRow(**UserCreateAllow.model_validate(attack).model_dump()).is_admin)
show("forbid", lambda: UserCreateForbid.model_validate(attack))
show("сирий dict з request.json()", lambda: UserRow(**attack).is_admin)

app = FastAPI()


@app.post("/users", status_code=201)
def create_user(body: UserCreateForbid) -> dict[str, str]:
    return {"name": body.name}


client = TestClient(app)
response = client.post("/users", json=attack)
print(f"   POST /users (forbid) → {response.status_code} {response.json()['detail'][0]['type']} {response.json()['detail'][0]['loc']}")
