"""Unit of Work: одна транзакція на кілька репозиторіїв. commit() — явно; вихід без commit() — ROLLBACK.

SqlUnitOfWork — над AsyncSession (сесія SQLAlchemy сама вже є Unit of Work; клас лише дає їй межі й імена).
FakeUnitOfWork — для тестів сервісів: ті самі репозиторії в пам'яті й та сама семантика rollback.
"""
import copy
from types import TracebackType
from typing import Protocol, Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .repositories import InMemoryNewsRepository, NewsRepository, SqlNewsRepository
from .tables import AuditRow


class AuditLog(Protocol):
    async def record(self, action: str, news_id: int | None) -> None: ...


class SqlAuditLog:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, action: str, news_id: int | None) -> None:
        self._session.add(AuditRow(action=action, news_id=news_id))


class InMemoryAuditLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, int | None]] = []

    async def record(self, action: str, news_id: int | None) -> None:
        self.entries.append((action, news_id))


class UnitOfWork(Protocol):
    @property
    def news(self) -> NewsRepository: ...      # property: лише читання — реалізація може мати вужчий тип
    @property
    def audit(self) -> AuditLog: ...

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None: ...
    async def commit(self) -> None: ...


class SqlUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._factory()
        self.news = SqlNewsRepository(self._session)
        self.audit = SqlAuditLog(self._session)
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        await self._session.rollback()          # після commit() — нічого не скасовує; без commit() — ROLLBACK
        await self._session.close()             # з'єднання повертається в пул

    async def commit(self) -> None:
        await self._session.commit()


class FakeUnitOfWork:
    """Зберігає стан на вході й відновлює його, якщо commit() не викликали — як справжня транзакція."""

    def __init__(self) -> None:
        self.news = InMemoryNewsRepository()
        self.audit = InMemoryAuditLog()
        self.commits = 0

    async def __aenter__(self) -> Self:
        self._snapshot = (copy.deepcopy(self.news.rows), list(self.audit.entries))
        self._committed = False
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                        tb: TracebackType | None) -> None:
        if not self._committed:
            self.news.rows, self.audit.entries = self._snapshot

    async def commit(self) -> None:
        self._committed = True
        self.commits += 1
