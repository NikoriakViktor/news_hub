"""Що SQLite пропускає, а PostgreSQL — ні. Ті самі запити на двох базах.

python demos/sqlite_vs_postgres.py                                            # лише SQLite
python demos/sqlite_vs_postgres.py postgresql+psycopg://test:test@localhost:5432/test
"""
import sys
from collections.abc import Callable

from sqlalchemy import Connection, create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, ".")
from newsapp.storage import Article, Base, make_engine  # noqa: E402


def too_long_varchar(conn: Connection) -> object:
    conn.execute(text("CREATE TEMP TABLE t1 (source VARCHAR(5))"))
    conn.execute(text("INSERT INTO t1 VALUES ('rbc.ua.com')"))
    return conn.scalar(text("SELECT source FROM t1"))


def text_in_integer(conn: Connection) -> object:
    conn.execute(text("CREATE TEMP TABLE t2 (n INTEGER)"))
    conn.execute(text("INSERT INTO t2 VALUES ('abc')"))
    return conn.scalar(text("SELECT n FROM t2"))


def foreign_key(conn: Connection) -> object:
    conn.execute(text("CREATE TEMP TABLE p (id INTEGER PRIMARY KEY)"))
    conn.execute(text("CREATE TEMP TABLE c (p_id INTEGER REFERENCES p(id))"))
    conn.execute(text("INSERT INTO c VALUES (42)"))                  # батьківського рядка 42 немає
    return "вставлено"


def like_case(conn: Connection) -> object:
    return conn.scalar(text("SELECT 'FastAPI' LIKE 'fastapi'"))


def lower_cyrillic(conn: Connection) -> object:
    return conn.scalar(text("SELECT lower('УРЯД')"))


CHECKS: list[tuple[str, Callable[[Connection], object]]] = [
    ("VARCHAR(5) ← 'rbc.ua.com'", too_long_varchar),
    ("INTEGER ← 'abc'", text_in_integer),
    ("REFERENCES без батька", foreign_key),
    ("'FastAPI' LIKE 'fastapi'", like_case),
    ("lower('УРЯД') без налаштувань", lower_cyrillic),
]


def run_checks(url: str) -> None:
    engine = create_engine(url)                      # навмисно без make_engine: як «за замовчуванням»
    print(f"--- {engine.dialect.name}")
    for title, check in CHECKS:
        with engine.connect() as conn:
            try:
                result = check(conn)
            except Exception as error:               # noqa: BLE001 — демо: показати будь-яку помилку бази
                result = f"{type(error).__name__}: {str(error.orig if hasattr(error, 'orig') else error).splitlines()[0]}"
            print(f"   {title:32} {result}")
            conn.rollback()
    engine.dispose()


def savepoint_rollback(engine_factory: Callable[[], object], label: str) -> None:
    """Транзакція на тест: COMMIT у тесті, потім ROLLBACK зовнішньої транзакції. Що лишилось у таблиці?"""
    engine = engine_factory()
    Base.metadata.create_all(engine)                 # type: ignore[arg-type]
    with engine.connect() as conn:                   # type: ignore[attr-defined]
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        session.add(Article(slug="s", title="Уряд ухвалив бюджет", source="rbc.ua"))
        session.commit()
        session.close()
        outer.rollback()
    with Session(engine) as session:                 # type: ignore[call-overload]
        print(f"   {label:32} рядків після відкату: {session.scalar(select(func.count()).select_from(Article))}")


if __name__ == "__main__":
    run_checks("sqlite://")
    if len(sys.argv) > 1:
        run_checks(sys.argv[1])
    print("--- транзакція на тест у SQLite")
    savepoint_rollback(lambda: create_engine("sqlite://", poolclass=StaticPool),
                       "create_engine за замовчуванням")
    savepoint_rollback(lambda: make_engine("sqlite://"), "make_engine (рецепт SAVEPOINT)")
