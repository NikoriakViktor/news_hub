"""SQLAlchemy 2 async: Core і ORM, сесія й identity map, ліниві зв'язки в async, N+1 і способи завантаження.

    python sqlalchemy_demo.py                          # SQLite (файл у тимчасовій папці)
    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres python sqlalchemy_demo.py
"""
import asyncio

from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload, raiseload, selectinload

from models import News, Source, count_queries, dialect, fresh_engine


def error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:110]}"


async def main() -> None:
    engine = await fresh_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    print("база:", dialect(engine))

    print("--- 1. Core: таблиці й рядки")
    news_table = News.__table__
    async with engine.connect() as conn:
        result = await conn.execute(
            select(news_table.c.id, news_table.c.title).where(news_table.c.lang == "ru").order_by(news_table.c.id))
        rows = result.all()
        print("   рядок Core:", rows[0], "| тип:", type(rows[0]).__name__, "| row.title:", rows[0].title)
        raw = await conn.execute(text("SELECT count(*) FROM news WHERE views > :min"), {"min": 500})
        print("   text() з параметром:", raw.scalar_one())

    print("--- 2. ORM: об'єкти, scalars, execute")
    async with sessions() as session:
        objs = (await session.scalars(select(News).where(News.lang == "ru").order_by(News.id))).all()
        print("   scalars(select(News)):", objs)
        pairs = (await session.execute(select(News.lang, func.count()).group_by(News.lang).order_by(News.lang))).all()
        print("   execute(select(стовпці)):", pairs)
        both = (await session.execute(select(News, Source.name).join(News.source).where(News.id == 1))).one()
        print("   execute(select(News, Source.name)):", both)

    print("--- 3. identity map: один рядок — один об'єкт у сесії")
    async with sessions() as session:
        with count_queries(engine) as sql:
            first = await session.get(News, 1)
            again = await session.get(News, 1)
            via_select = await session.scalar(select(News).where(News.id == 1))
        print("   get(1) is get(1):", first is again, "| select(...) is get(1):", via_select is first,
              "| SQL-запитів:", len(sql))
        first.views = 999                      # змінили об'єкт у пам'яті, не в базі
        fresh = await session.scalar(select(News).where(News.id == 1))
        print("   після views = 999 і нового SELECT:", fresh.views, "(autoflush відправив UPDATE до SELECT)")
        await session.rollback()

    print("--- 4. ліниве завантаження в async")
    async with sessions() as session:
        item = await session.get(News, 1)
        try:
            print(item.source)
        except Exception as exc:  # noqa: BLE001 — показуємо саму помилку
            print("   item.source         ", error(exc))
        print("   awaitable_attrs     ", await item.awaitable_attrs.source)
        await session.refresh(item, ["source"])
        print("   після refresh       ", item.source)
        strict = await session.scalar(select(News).where(News.id == 2).options(raiseload("*")))
        try:
            print(strict.source)
        except Exception as exc:  # noqa: BLE001
            print("   raiseload('*')      ", error(exc))

    print("--- 5. N+1: джерела і їхні новини (один-до-багатьох)")
    async with sessions() as session:
        with count_queries(engine) as sql:
            sources = (await session.scalars(select(Source).order_by(Source.id))).all()
            counts = {s.name: len(await s.awaitable_attrs.news) for s in sources}
        print("   awaitable_attrs у циклі:", counts, "| SQL-запитів:", len(sql))

    for title, option in (("selectinload", selectinload(Source.news)), ("joinedload", joinedload(Source.news))):
        async with sessions() as session:
            with count_queries(engine) as sql:
                result = await session.scalars(select(Source).options(option).order_by(Source.id))
                sources = result.unique().all()
                counts = {s.name: len(s.news) for s in sources}
            print(f"   {title:23} {counts} | SQL-запитів: {len(sql)}")
            for statement in sql:
                print("      SQL:", statement[:320])

    async with sessions() as session:
        try:
            (await session.scalars(select(Source).options(joinedload(Source.news)))).all()
        except Exception as exc:  # noqa: BLE001
            print("   joinedload без unique():", error(exc))

    print("--- 6. N+1: новини і їхнє джерело (багато-до-одного)")
    async with sessions() as session:
        with count_queries(engine) as sql:
            items = (await session.scalars(select(News).order_by(News.id))).all()
            names = [(await n.awaitable_attrs.source).name for n in items]
        print(f"   {len(items)} новин, {len(set(names))} різні джерела | SQL-запитів: {len(sql)}")

    print("--- 7. LIMIT і joinedload колекції")
    async with sessions() as session:
        with count_queries(engine) as sql:
            result = await session.scalars(select(Source).options(joinedload(Source.news)).order_by(Source.id).limit(2))
            top = result.unique().all()
        print("   2 джерела:", {s.name: len(s.news) for s in top})
        print("      SQL:", sql[0][:420])

    print("--- 8. insert(...).returning і ORM-масовий запис")
    async with sessions() as session:
        new_ids = (await session.scalars(insert(Source).returning(Source.id),
                                         [{"name": "lb.ua"}, {"name": "nv.ua"}])).all()
        print("   insert().returning(id):", new_ids)
        await session.rollback()

    print("--- 9. SQL-вираз в атрибуті: row.views = News.views + 1")
    async with sessions() as session:
        row = await session.get(News, 1)
        row.views = News.views + 1
        print("   до flush:    ", type(row.views).__name__, row.views)
        await session.flush()
        try:
            print(row.views)
        except Exception as exc:  # noqa: BLE001
            print("   після flush: ", error(exc))
        await session.refresh(row, ["views"])
        print("   після refresh:", row.views)
        await session.rollback()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
