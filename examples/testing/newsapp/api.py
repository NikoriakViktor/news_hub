"""FastAPI-застосунок прикладу: lifespan, залежності, middleware, помилки 404/409/422/500.

Запуск: uvicorn newsapp.api:app --reload  (база — SQLite у пам'яті; NEWSAPP_DATABASE_URL — інша)
"""
import os
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .digest import send_digest
from .mail import Mailer, SmtpMailer
from .storage import Article, ArticleRepo, Base, make_engine

DATABASE_URL = os.getenv("NEWSAPP_DATABASE_URL", "sqlite://")
REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = make_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    app.state.session_factory = sessionmaker(engine, expire_on_commit=False)
    app.state.mailer = SmtpMailer()
    yield
    engine.dispose()


app = FastAPI(title="newsapp", lifespan=lifespan)


@app.middleware("http")
async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """X-Request-ID клієнта, якщо він безпечний; інакше — новий. Той самий id — у відповіді."""
    incoming = request.headers.get("X-Request-ID", "")
    rid = incoming if REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


def get_db(request: Request) -> Iterator[Session]:
    """Сесія на запит: COMMIT, якщо ендпоінт успішний, ROLLBACK — якщо впав."""
    with request.app.state.session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_mailer(request: Request) -> Mailer:
    return request.app.state.mailer       # type: ignore[no-any-return]


DbDep = Annotated[Session, Depends(get_db)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]


class ArticleIn(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    source: str = Field(min_length=2, max_length=20)


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slug: str
    title: str
    source: str


class DigestIn(BaseModel):
    subscribers: list[str] = Field(min_length=1, max_length=100)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/articles", status_code=201, response_model=ArticleOut)
def create_article(data: ArticleIn, db: DbDep) -> Article:
    try:
        return ArticleRepo(db).add(data.title, data.source)
    except ValueError as error:                     # slugify: у заголовку немає жодного слова
        raise HTTPException(422, str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "новина з таким slug уже є") from error


@app.get("/articles", response_model=list[ArticleOut])
def search_articles(db: DbDep, q: Annotated[str, Query(min_length=2, max_length=50)]) -> list[Article]:
    return ArticleRepo(db).search(q)


@app.get("/articles/{slug}", response_model=ArticleOut)
def get_article(slug: str, db: DbDep) -> Article:
    article = ArticleRepo(db).get(slug)
    if article is None:
        raise HTTPException(404, "новину не знайдено")
    return article


@app.post("/digest")
def digest(data: DigestIn, db: DbDep, mailer: MailerDep) -> dict[str, list[str]]:
    return send_digest(data.subscribers, ArticleRepo(db).latest_titles(), mailer)
