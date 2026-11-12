"""Таблиця новин і репозиторій (SQLAlchemy 2, синхронно)."""
from typing import Any

from sqlalchemy import Engine, String, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from .text import slugify


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20))           # VARCHAR(20): SQLite довжину не перевіряє


def make_engine(url: str) -> Engine:
    """sqlite:// у пам'яті — одне з'єднання на всіх (StaticPool); для SQLite — SAVEPOINT і lower() з кирилицею."""
    if not url.startswith("sqlite"):
        return create_engine(url)
    options: dict[str, Any] = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}} \
        if url in ("sqlite://", "sqlite+pysqlite://") else {}
    engine = create_engine(url, **options)
    event.listen(engine, "connect", _sqlite_connect)
    event.listen(engine, "begin", lambda conn: conn.exec_driver_sql("BEGIN"))
    return engine


def _sqlite_connect(dbapi_connection: Any, _record: Any) -> None:
    # 1. sqlite3 сам відкриває й закриває транзакції і ламає SAVEPOINT: вимикаємо — BEGIN шле SQLAlchemy
    #    (рецепт з документації SQLAlchemy «Serializable isolation / Savepoints / Transactional DDL»)
    dbapi_connection.isolation_level = None
    # 2. вбудований lower() у SQLite знає лише латиницю: lower('УРЯД') == 'УРЯД'
    dbapi_connection.create_function("lower", 1, lambda s: s.lower() if isinstance(s, str) else s,
                                     deterministic=True)


class ArticleRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, title: str, source: str) -> Article:
        """INSERT без COMMIT: транзакцією керує той, хто дав сесію (get_db або тест)."""
        article = Article(slug=slugify(title), title=title, source=source)
        self.session.add(article)
        self.session.flush()                    # IntegrityError (той самий slug) — тут, а не при COMMIT
        return article

    def get(self, slug: str) -> Article | None:
        return self.session.scalar(select(Article).where(Article.slug == slug))

    def search(self, q: str) -> list[Article]:
        """Без урахування регістру: lower(title) LIKE lower('%q%'); % і _ у q — звичайні символи."""
        stmt = select(Article).where(Article.title.icontains(q, autoescape=True)).order_by(Article.id)
        return list(self.session.scalars(stmt))

    def latest_titles(self, limit: int = 10) -> list[str]:
        return list(self.session.scalars(select(Article.title).order_by(Article.id.desc()).limit(limit)))
