"""Транзакції з SQLAlchemy async: commit/rollback, зламана сесія, expire_on_commit, SAVEPOINT,
конкурентні оновлення (втрачене оновлення, FOR UPDATE, атомарний UPDATE), ON CONFLICT, рівні ізоляції.

    python transactions_demo.py                    # SQLite: розділ 7 пропускається (лише PostgreSQL)
    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres python transactions_demo.py
"""
import asyncio

from sqlalchemy import func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from models import News, Source, dialect, fresh_engine


def error(exc: BaseException) -> str:
    text = str(exc.orig if isinstance(exc, DBAPIError) and exc.orig else exc).splitlines()[0]
    if text.startswith("("):                                      # "(sqlalchemy.exc.X) текст" → "текст"
        text = text.split(") ", 1)[-1]
    return f"{type(exc).__name__}: {text[:105]}"


async def views(engine: AsyncEngine, news_id: int = 1) -> int:
    async with AsyncSession(engine) as session:
        return await session.scalar(select(News.views).where(News.id == news_id))


async def set_views(engine: AsyncEngine, news_id: int, value: int) -> None:
    """Інший запит: окрема сесія, окреме з'єднання, власний COMMIT."""
    async with AsyncSession(engine) as session, session.begin():
        await session.execute(update(News).where(News.id == news_id).values(views=value))


async def main() -> None:
    engine = await fresh_engine()
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    is_pg = dialect(engine) == "postgresql"
    print("база:", dialect(engine))

    print("--- 1. все або нічого")
    try:
        async with sessions() as session, session.begin():      # begin(): COMMIT наприкінці, ROLLBACK при винятку
            session.add(Source(name="lb.ua"))
            (await session.get(News, 1)).views = -5                # CHECK (views >= 0) порушиться при flush
    except IntegrityError as exc:
        print("   ", error(exc))
    async with sessions() as session:
        print("    lb.ua у базі:", await session.scalar(select(func.count()).where(Source.name == "lb.ua")),
              "| views новини 1:", await views(engine))

    print("--- 2. помилка flush ламає сесію до rollback()")
    async with sessions() as session:
        session.add(Source(name="rbc.ua"))                          # дубль UNIQUE
        try:
            await session.flush()
        except IntegrityError as exc:
            print("    flush:          ", error(exc))
        try:
            await session.get(News, 2)
        except Exception as exc:  # noqa: BLE001 — показуємо саму помилку
            print("    наступний запит:", error(exc))
        await session.rollback()
        print("    після rollback():", await session.get(News, 2))

    print("--- 3. expire_on_commit")
    for expire in (True, False):
        async with async_sessionmaker(engine, expire_on_commit=expire)() as session:
            item = await session.get(News, 3)
            item.views += 1
            await session.commit()
            try:
                print(f"    expire_on_commit={expire!s:5} після commit item.views =", item.views)
            except Exception as exc:  # noqa: BLE001
                print(f"    expire_on_commit={expire!s:5} після commit item.views →", error(exc))
    async with sessions() as session:
        item = await session.get(News, 3)
        await session.commit()
        await set_views(engine, 3, 0)                              # інший запит змінив рядок
        print("    expire_on_commit=False, рядок змінили після commit: item.views =", item.views,
              "| у базі:", await views(engine, 3))

    print("--- 4. SAVEPOINT: зберегти добрі рядки, пропустити погані")
    async with sessions() as session, session.begin():
        saved, skipped = 0, 0
        for name in ("lb.ua", "rbc.ua", "nv.ua"):                 # rbc.ua уже є
            try:
                async with session.begin_nested():                 # SAVEPOINT
                    session.add(Source(name=name))
                saved += 1
            except IntegrityError:
                skipped += 1                                       # ROLLBACK TO SAVEPOINT — лише цей рядок
        print(f"    додано {saved}, пропущено {skipped}")
    async with sessions() as session:
        print("    джерела:", (await session.scalars(select(Source.name).order_by(Source.id))).all())

    print("--- 5. ON CONFLICT: вставити або оновити одним оператором")
    insert = postgresql.insert if is_pg else sqlite.insert
    async with sessions() as session, session.begin():
        rows = [{"source_id": 1, "url": "https://example.com/1", "title": "Гривня зміцнилася (оновлено)",
                 "lang": "uk", "views": 0},
                {"source_id": 1, "url": "https://example.com/100", "title": "Нова новина", "lang": "uk", "views": 0}]
        nothing = insert(News).values(rows).on_conflict_do_nothing(index_elements=["url"]).returning(News.id)
        print("    DO NOTHING  → вставлено id:", (await session.scalars(nothing)).all())
        stmt = insert(News).values(rows[:1] + [{**rows[1], "url": "https://example.com/101"}])
        upsert = stmt.on_conflict_do_update(index_elements=["url"], set_={"title": stmt.excluded.title}) \
            .returning(News.id, News.title)
        print("    DO UPDATE   → ", (await session.execute(upsert)).all())

    print("--- 6. десять запитів одночасно: +1 перегляд кожен")

    async def read_modify_write(lock: bool) -> None:
        async with sessions() as session, session.begin():
            stmt = select(News).where(News.id == 1)
            item = await session.scalar(stmt.with_for_update() if lock else stmt)
            await asyncio.sleep(0.05)                              # ендпоінт ще щось робить
            item.views = item.views + 1

    async def atomic() -> None:
        async with sessions() as session, session.begin():
            await session.execute(update(News).where(News.id == 1).values(views=News.views + 1))

    for title, job in (("прочитати → +1 → записати", lambda: read_modify_write(False)),
                       ("SELECT … FOR UPDATE", lambda: read_modify_write(True)),
                       ("UPDATE SET views = views + 1", atomic)):
        before = await views(engine)
        await asyncio.gather(*(job() for _ in range(10)))
        print(f"    {title:30} було {before}, 10 запитів → стало {await views(engine)} (+{await views(engine) - before})")
    print("    SQL з with_for_update():", str(select(News.id).where(News.id == 1).with_for_update()
                                           .compile(dialect=engine.dialect)).replace("\n", " "))

    if not is_pg:
        print("--- 7. лише PostgreSQL: запусти з DATABASE_URL=postgresql+asyncpg://...")
        await engine.dispose()
        return

    print("--- 7. рівні ізоляції")

    async def two_reads(level: str) -> None:
        reader_engine = engine.execution_options(isolation_level=level)
        async with AsyncSession(reader_engine) as reader, reader.begin():
            first = await reader.scalar(select(News.views).where(News.id == 2))
            await set_views(engine, 2, first + 100)                # інша транзакція змінила рядок і COMMIT
            second = await reader.scalar(select(News.views).where(News.id == 2))
            print(f"    {level:16} перше читання {first}, друге {second}")

    await two_reads("READ COMMITTED")
    await two_reads("REPEATABLE READ")

    repeatable = engine.execution_options(isolation_level="REPEATABLE READ")
    try:
        async with AsyncSession(repeatable) as session, session.begin():
            item = await session.scalar(select(News).where(News.id == 2))
            await set_views(engine, 2, 0)
            item.views += 1
            await session.flush()
    except DBAPIError as exc:
        print("    REPEATABLE READ + чужий UPDATE того самого рядка:", error(exc))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
