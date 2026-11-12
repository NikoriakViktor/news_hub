"""SQL-ін'єкція в SQLAlchemy: f-рядок у text(), параметри, сортування за полем від клієнта, % і _ у LIKE.

    python injection_demo.py
    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres python injection_demo.py
"""
import asyncio

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models import News, dialect, fresh_engine

SORTABLE = {"id": News.id, "views": News.views, "title": News.title}   # білий список полів сортування


def error(exc: Exception) -> str:
    message = str(getattr(exc, "orig", exc)).splitlines()[0]
    return f"{type(exc).__name__}: {message.split(') ', 1)[-1][:100]}"


async def main() -> None:
    engine = await fresh_engine()
    print("база:", dialect(engine))
    attack = "x' OR '1'='1"
    async with AsyncSession(engine) as session:
        print("--- 1. пошук за мовою з рядка запиту ?lang=")
        unsafe = await session.execute(text(f"SELECT count(*) FROM news WHERE lang = '{attack}'"))
        print("    f-рядок у text():        ", unsafe.scalar_one(), "рядків (усі новини)")
        safe = await session.execute(text("SELECT count(*) FROM news WHERE lang = :lang"), {"lang": attack})
        print("    text() з :lang:          ", safe.scalar_one())
        orm = await session.scalar(select(News.id).where(News.lang == attack))
        print("    select().where(...):     ", orm)

        print("--- 2. ?sort= : назву стовпця параметром не передаси")
        try:
            await session.execute(text("SELECT id FROM news ORDER BY :col"), {"col": "views"})
            print("    ORDER BY :col → виконалось, але сортує за константою, а не за стовпцем")
        except Exception as exc:  # noqa: BLE001
            print("    ORDER BY :col →", error(exc))
        await session.rollback()
        for sort in ("views", "views; DROP TABLE news"):
            column = SORTABLE.get(sort)
            if column is None:
                print(f"    sort={sort!r:28} → 422: дозволено {sorted(SORTABLE)}")
                continue
            ids = (await session.scalars(select(News.id).order_by(column.desc()).limit(3))).all()
            print(f"    sort={sort!r:28} → {ids}")

        print("--- 3. ?q= : % і _ у LIKE — теж «код»")
        for q in ("%", "_", "зміц"):
            plain = len((await session.scalars(select(News.id).where(News.title.icontains(q)))).all())
            escaped = len((await session.scalars(select(News.id).where(News.title.icontains(q, autoescape=True)))).all())
            print(f"    q={q!r:7} icontains: {plain} | icontains(autoescape=True): {escaped}")
        print("    SQL:", select(News.id).where(News.title.icontains("50%", autoescape=True))
              .compile(engine, compile_kwargs={"literal_binds": True}).string.replace("\n", " "))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
