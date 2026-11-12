"""FastAPI з пулом asyncpg напряму, без SQLAlchemy: пул у lifespan, з'єднання на запит через Depends.

    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres python asyncpg_app.py
"""
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

DSN = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg", "postgresql")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pool = await asyncpg.create_pool(DSN, min_size=2, max_size=10, command_timeout=30)
    async with app.state.pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS pg_news")
        await conn.execute("CREATE TABLE pg_news (id int PRIMARY KEY, title text NOT NULL)")
        await conn.executemany("INSERT INTO pg_news VALUES ($1, $2)", [(1, "Гривня зміцнилася"), (2, "Нові поїзди")])
    yield
    await app.state.pool.close()                     # закрити всі з'єднання пулу


app = FastAPI(lifespan=lifespan)


async def get_conn(request: Request) -> AsyncIterator[asyncpg.Connection]:
    async with request.app.state.pool.acquire() as conn:     # повернеться в пул після запиту
        yield conn


ConnDep = Annotated[asyncpg.Connection, Depends(get_conn)]


@app.get("/news/{news_id}")
async def get_news(news_id: int, conn: ConnDep) -> dict[str, object]:
    row = await conn.fetchrow("SELECT id, title FROM pg_news WHERE id = $1", news_id)   # $1 — параметр
    if row is None:
        raise HTTPException(404, "news not found")
    return dict(row)


@app.get("/pool")
async def pool_status(request: Request) -> dict[str, int]:
    pool = request.app.state.pool
    return {"size": pool.get_size(), "idle": pool.get_idle_size(), "max": pool.get_max_size()}


if __name__ == "__main__":
    if not DSN.startswith("postgresql"):
        sys.exit("потрібен PostgreSQL: DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres")
    with TestClient(app) as client:
        for path in ("/news/1", "/news/99", "/pool"):
            response = client.get(path)
            print(f"GET {path:9} → {response.status_code} {response.json()}")
