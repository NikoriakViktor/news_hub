"""Unit of Work і фейки: що ховає фейк без семантики транзакції; SAVEPOINT у SQLite.

    python uow_demo.py
    DATABASE_URL=postgresql+asyncpg://postgres:x@localhost:5544/postgres python uow_demo.py
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import database_url
from news_app.repositories import InMemoryNewsRepository
from news_app.services import Rejected, publish
from news_app.tables import AuditRow, Base, NewsRow, fix_sqlite_transactions
from news_app.uow import FakeUnitOfWork, InMemoryAuditLog, SqlUnitOfWork, UnitOfWork


class NaiveFakeUnitOfWork:
    """Поширений фейк: commit() лише ставить прапорець, rollback не робить нічого."""

    def __init__(self) -> None:
        self.news, self.audit, self.committed = InMemoryNewsRepository(), InMemoryAuditLog(), False

    async def __aenter__(self) -> "NaiveFakeUnitOfWork":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True


async def publish_forgot_commit(uow: UnitOfWork, url: str, title: str) -> None:
    """Помилка в сервісі: забули await uow.commit()."""
    async with uow:
        item = await uow.news.add(url, title)
        await uow.audit.record("publish", item.id)


async def visible(uow: UnitOfWork) -> int:
    async with uow:
        return len(await uow.news.latest(10))


async def fresh_factory(fix_sqlite: bool = True) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url())
    if fix_sqlite and engine.dialect.name == "sqlite":
        fix_sqlite_transactions(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


async def main() -> None:
    factory = await fresh_factory()
    print("база:", factory.kw["bind"].dialect.name)

    print("--- 1. сервіс забув commit(): скільки новин видно після")
    for uow in (NaiveFakeUnitOfWork(), FakeUnitOfWork(), SqlUnitOfWork(await fresh_factory())):
        await publish_forgot_commit(uow, "https://example.com/1", "Гривня зміцнилася")
        print(f"    {type(uow).__name__:20} {await visible(uow)}")

    print("--- 2. модерація відхилила новину після add і record")
    for uow in (NaiveFakeUnitOfWork(), FakeUnitOfWork(), SqlUnitOfWork(await fresh_factory())):
        try:
            await publish(uow, "https://example.com/1", "Найкраще казино країни")
        except Rejected:
            pass
        print(f"    {type(uow).__name__:20} новин: {await visible(uow)}")

    print("--- 3. SAVEPOINT без зовнішньої транзакції")
    for fix in (False, True):
        factory = await fresh_factory(fix_sqlite=fix)
        async with factory() as session:
            async with session.begin_nested():                  # SAVEPOINT … RELEASE
                session.add(NewsRow(url="https://example.com/1", title="Гривня зміцнилася"))
            session.add(AuditRow(action="publish", news_id=1))
            await session.rollback()                            # скасувати все
        async with factory() as session:
            news = len((await session.scalars(select(NewsRow))).all())
            audit = len((await session.scalars(select(AuditRow))).all())
        label = "з fix_sqlite_transactions" if fix else "без виправлення"
        print(f"    {label:26} після rollback: news={news}, audit={audit}")


if __name__ == "__main__":
    asyncio.run(main())
