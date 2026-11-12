"""Спільні фікстури: база з відкатом на кожен тест, клієнти API, фабрика новин, фейкова пошта.

База — SQLite у пам'яті; ті самі тести на PostgreSQL:
    TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:5432/test pytest
"""
import itertools
import os
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from newsapp.api import app, get_db, get_mailer
from newsapp.storage import Article, ArticleRepo, Base, make_engine
from tests.fakes import FakeMailer

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite://")
WORKER = os.getenv("PYTEST_XDIST_WORKER", "main")       # pytest -n 2 → gw0, gw1: у кожного своя схема


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """@pytest.mark.postgres без PostgreSQL — skip з причиною, а не червоний тест."""
    if TEST_DATABASE_URL.startswith("sqlite"):
        skip = pytest.mark.skip(reason="потрібен PostgreSQL: задай TEST_DATABASE_URL")
        for item in items:
            if "postgres" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Одна база на весь прогін: таблиці створюються раз, дані відкочуються після кожного тесту."""
    engine = make_engine(TEST_DATABASE_URL)
    schema = f"test_{WORKER}"
    postgres = engine.dialect.name == "postgresql"
    if postgres:                                            # паралельні воркери — кожен у своїй схемі
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    if postgres:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """Транзакція на тест: усе, що записали тест і застосунок (навіть з COMMIT), відкочується."""
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        yield session
        session.close()
        transaction.rollback()


@pytest.fixture
def make_article(db: Session) -> Callable[..., Article]:
    """Фабрика: make_article(title="…") — у тесті видно лише поля, важливі для перевірки."""
    numbers = itertools.count(1)

    def factory(title: str | None = None, source: str = "rbc.ua") -> Article:
        return ArticleRepo(db).add(title or f"Новина номер {next(numbers)}", source)

    return factory


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def client(db: Session, mailer: FakeMailer) -> Iterator[TestClient]:
    """API над тестовою сесією і фейковою поштою; lifespan запускається (with), підміни прибираються."""
    def test_get_db() -> Iterator[Session]:              # той самий контракт, що newsapp.api.get_db
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = test_get_db
    app.dependency_overrides[get_mailer] = lambda: mailer
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
