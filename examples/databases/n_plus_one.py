"""N+1 на більших даних: 500 джерел × 4 новини. Скільки запитів і скільки часу.

    python n_plus_one.py
    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres python n_plus_one.py
"""
import asyncio
import time

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import joinedload, selectinload

from models import News, Source, count_queries, dialect, fresh_engine

SOURCES, PER_SOURCE = 500, 4


async def main() -> None:
    engine = await fresh_engine()
    async with engine.begin() as conn:
        await conn.execute(delete(News))
        await conn.execute(delete(Source))
        await conn.execute(insert(Source), [{"id": i, "name": f"source-{i}"} for i in range(1, SOURCES + 1)])
        await conn.execute(insert(News), [
            {"source_id": s, "url": f"https://example.com/{s}/{k}", "title": f"Новина {k}", "lang": "uk", "views": k}
            for s in range(1, SOURCES + 1) for k in range(PER_SOURCE)])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    print(f"база: {dialect(engine)}; {SOURCES} джерел × {PER_SOURCE} новини")

    async def lazy_loop(session):
        sources = (await session.scalars(select(Source).order_by(Source.id))).all()
        return sum([len(await s.awaitable_attrs.news) for s in sources])

    async def eager(session, option):
        result = await session.scalars(select(Source).options(option).order_by(Source.id))
        return sum(len(s.news) for s in result.unique().all())

    async def group_by(session):
        rows = await session.execute(select(News.source_id, func.count()).group_by(News.source_id))
        return sum(n for _, n in rows)

    variants = {
        "awaitable_attrs у циклі": lazy_loop,
        "selectinload": lambda s: eager(s, selectinload(Source.news)),
        "joinedload": lambda s: eager(s, joinedload(Source.news)),
        "GROUP BY (лише лічильники)": group_by,
    }
    for title, run in variants.items():
        best = float("inf")
        for _ in range(3):                      # найкращий з трьох запусків
            async with sessions() as session:
                with count_queries(engine) as sql:
                    started = time.perf_counter()
                    total = await run(session)
                    best = min(best, time.perf_counter() - started)
        print(f"   {title:28} новин: {total} | запитів: {len(sql):4} | {best * 1000:7.1f} мс")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
