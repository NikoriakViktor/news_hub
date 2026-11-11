"""HttpUrl, AnyUrl, EmailStr, AwareDatetime: що приймають, що повертають і як зберегти в базу.

    pip install "pydantic[email]" sqlalchemy fastapi httpx
    python types_demo.py
"""
import json
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, EmailStr, HttpUrl, NaiveDatetime, TypeAdapter, ValidationError
from sqlalchemy import DateTime, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def check(tp: object, value: object) -> str:
    try:
        result = TypeAdapter(tp).validate_python(value)
        return f"{result!s:38} ({type(result).__name__})"
    except ValidationError as exc:
        error = exc.errors()[0]
        return f"✗ {error['type']}: {error['msg'][:60]}"


print("--- 1. HttpUrl і AnyUrl")
for value in ("https://Example.COM", "https://example.com/a b?q=1#top", "http://127.0.0.1:8080/admin",
              "http://user:pass@example.com", "ftp://example.com/file", "file:///etc/passwd", "not-a-valid-url",
              "https://пример.укр/"):
    print(f"   {value!r:36} HttpUrl: {check(HttpUrl, value)}")
    print(f"   {'':36} AnyUrl:  {check(AnyUrl, value)}")

url = TypeAdapter(HttpUrl).validate_python("https://www.rbc.ua/ukr/news/x.html?utm=1")
print("--- 2. що всередині HttpUrl")
print(f"   isinstance(url, str)={isinstance(url, str)} scheme={url.scheme} host={url.host} port={url.port} "
      f"path={url.path} query={url.query}")
print(f"   url == 'https://www.rbc.ua/ukr/news/x.html?utm=1': {url == 'https://www.rbc.ua/ukr/news/x.html?utm=1'}"
      f" | str(url) == ...: {str(url) == 'https://www.rbc.ua/ukr/news/x.html?utm=1'}")


class Link(BaseModel):
    url: HttpUrl


link = Link(url="https://example.com")
print("--- 3. серіалізація")
print("   model_dump():", link.model_dump())
print("   model_dump(mode='json'):", link.model_dump(mode="json"))
try:
    json.dumps(link.model_dump())
except TypeError as exc:
    print("   json.dumps(model_dump()):", exc)
print("   json.dumps(..., default=str):", json.dumps(link.model_dump(), default=str))


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    website: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


engine = create_engine("sqlite://")
Base.metadata.create_all(engine)
print("--- 4. у базу")
with Session(engine) as session:
    try:
        session.add(Company(website=link.url, created_at=datetime.fromisoformat("2026-11-11T12:00:00+02:00")))
        session.commit()
    except Exception as exc:
        session.rollback()
        print("   website=link.url:", type(exc).__name__, str(exc).splitlines()[0][:100])
    session.add(Company(website=str(link.url), created_at=datetime.fromisoformat("2026-11-11T12:00:00+02:00")))
    session.commit()
    row = session.scalars(select(Company)).one()
    print(f"   website=str(link.url): {row.website!r}; created_at з SQLite: {row.created_at!r}")


print("--- 5. EmailStr")
for value in ("Olena@Example.COM", "olena@localhost", "not-an-email", "olena.@example.com", "олена@приклад.укр"):
    print(f"   {value!r:24} {check(EmailStr, value)}")


print("--- 6. datetime, AwareDatetime, NaiveDatetime")
for value in ("2026-11-11T12:00:00+02:00", "2026-11-11T12:00:00Z", "2026-11-11T12:00:00", 1_700_000_000):
    print(f"   {value!r:28} datetime: {check(datetime, value)}")
    print(f"   {'':28} Aware:    {check(AwareDatetime, value)}")
    print(f"   {'':28} Naive:    {check(NaiveDatetime, value)}")


print("--- 7. AwareDatetime у відповіді, а в базі SQLite")
class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    website: HttpUrl
    created_at: AwareDatetime


app = FastAPI()


@app.get("/company", response_model=CompanyOut)
def company() -> Company:
    with Session(engine) as session:
        return session.scalars(select(Company)).one()


response = TestClient(app, raise_server_exceptions=False).get("/company")
print("  ", response.status_code, response.text[:80])
schema = app.openapi()["components"]["schemas"]["CompanyOut"]["properties"]
print("   OpenAPI:", schema["website"], schema["created_at"])
