"""Модель на версії head (0004). Alembic порівнює її з базою в autogenerate і `alembic check`."""
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500), unique=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    category: Mapped[str] = mapped_column(String(100))        # 0002 додала (nullable), 0003 зробила NOT NULL
