"""FastAPI поверх сервісу: ендпоінт отримує UnitOfWork через Depends, тести підміняють його фейком.

    uvicorn news_app.api:app --reload          # SQLite у тимчасовій папці; DATABASE_URL — інша база
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models import database_url

from .repositories import DuplicateUrl, News
from .services import Rejected, publish
from .tables import Base
from .uow import SqlUnitOfWork, UnitOfWork

engine = create_async_engine(database_url())
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)     # для прикладу; у проєкті — Alembic
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)


def get_uow() -> UnitOfWork:
    return SqlUnitOfWork(SessionFactory)


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


class NewsIn(BaseModel):
    url: str = Field(max_length=500)
    title: str = Field(min_length=5, max_length=300)


@app.post("/news", status_code=201)
async def create_news(body: NewsIn, uow: UowDep) -> News:
    try:
        return await publish(uow, body.url, body.title)
    except DuplicateUrl:
        raise HTTPException(409, "news with this url already exists") from None
    except Rejected:
        raise HTTPException(422, "title rejected by moderation") from None


@app.get("/news")
async def latest_news(uow: UowDep, limit: int = 10) -> list[News]:
    async with uow:
        return await uow.news.latest(limit)
